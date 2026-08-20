"""
Host-based IDS — run on VM1 or VM2 (the defender side, not the attacker box).

Three independent detectors, all passive/read-only:

  1. ARP integrity monitor — polls the local ARP/neighbor table for the
     trusted peer's IP and alerts the instant its MAC changes. Catches
     ARP spoofing directly, regardless of whether static ARP entries
     are also in place (defence in depth — this is the *detect* layer,
     static ARP is the *prevent* layer).

  2. Modbus write whitelist check — watches port 502 traffic and alerts
     on any coil/register write from an IP that isn't the configured
     legitimate master. Logs attempts even if a firewall is already
     blocking them, so you have visibility into what was tried.

  3. Physical plausibility check — tracks each DNP3 analog value's
     normal rate of change and alerts when a new reading is physically
     implausible (e.g. winding temp jumping 87 -> 300 in one poll).
     This is the last line of defence: it doesn't care *how* a bad
     value arrived (MITM, tamper, compromised master, whatever) — it
     just checks whether the number makes physical sense.

--- config ---
Update PEER_IP / PEER_MAC / LEGITIMATE_MASTER_IP below to match your
current lab addressing before running (IPs have drifted a lot this
session — MACs are stable since they're tied to the virtual NIC).

--- run ---
    sudo python3 ids_monitor.py

Ctrl+C to stop. All alerts also append to ids_alerts.log.
"""

from scapy.all import sniff, IP, TCP, Raw
from datetime import datetime
import subprocess
import threading
import struct
import time
import re

# ============================================================
# config — update these for your current lab addressing
# ============================================================
PEER_IP  = "10.80.128.206"        # the other trusted VM this host talks to
PEER_MAC = "08:00:27:04:e1:8b"    # that VM's known-good MAC (stable across IP changes)
IFACE    = "enp0s3"

LEGITIMATE_MASTER_IP = "10.80.128.206"   # only this IP may write Modbus
MODBUS_PORT = 502
DNP3_PORT   = 20000

ARP_POLL_SECONDS = 2

# max plausible change between consecutive readings, per tag.
# THESE ARE ILLUSTRATIVE LAB THRESHOLDS, not engineering-validated
# limits — a real deployment would set these from the process's
# actual physical characteristics (thermal time constants, etc.)
MAX_DELTA = {
    "T1_WindingTemp_C": 15,     # thermal systems don't jump this much in one poll
    "Bus1_Voltage_kV":  200,
    "FeederCurrent_A":  150,
    "Breaker_OpCount":  2,      # should basically only ever increment by 1
}
ANALOG_LABELS = {1: "Gauge", 2: "Bus1_Voltage_kV", 3: "FeederCurrent_A",
                  4: "T1_WindingTemp_C", 5: "Breaker_OpCount"}

LOG_FILE = "ids_alerts.log"
logf = open(LOG_FILE, "a", buffering=1)

def alert(source, message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{source}] ALERT: {message}"
    print(f"\033[91m{line}\033[0m")  # red
    logf.write(line + "\n")

def info(source, message):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{source}] {message}")

# ============================================================
# 1. ARP integrity monitor
# ============================================================
def arp_monitor():
    info("ARP", f"watching {PEER_IP} — expecting MAC {PEER_MAC}")
    last_seen_mac = PEER_MAC
    while True:
        try:
            out = subprocess.run(["ip", "neigh", "show", PEER_IP],
                                  capture_output=True, text=True, timeout=3).stdout
            m = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", out)
            if m:
                current_mac = m.group(1).lower()
                if current_mac != last_seen_mac.lower():
                    alert("ARP", f"{PEER_IP} MAC changed! expected {last_seen_mac}, "
                                  f"now {current_mac} — possible ARP spoofing in progress")
                    last_seen_mac = current_mac
        except Exception as e:
            pass
        time.sleep(ARP_POLL_SECONDS)

# ============================================================
# 2. Modbus write whitelist
# ============================================================
def check_modbus(pkt):
    if not (pkt.haslayer(IP) and pkt.haslayer(TCP) and pkt.haslayer(Raw)):
        return
    if pkt[TCP].dport != MODBUS_PORT:
        return
    raw = bytes(pkt[Raw].load)
    if len(raw) < 8:
        return
    proto = struct.unpack(">H", raw[2:4])[0]
    if proto != 0:
        return
    func = raw[7]
    if func in (0x05, 0x06, 0x0F, 0x10):  # any write function
        src = pkt[IP].src
        if src != LEGITIMATE_MASTER_IP:
            detail = ""
            if func == 0x05 and len(raw) >= 12:
                addr = struct.unpack(">H", raw[8:10])[0]
                val = struct.unpack(">H", raw[10:12])[0]
                detail = f" (coil {addr} -> {'ON' if val==0xFF00 else 'OFF'})"
            alert("MODBUS", f"write from unauthorized source {src}{detail} — "
                             f"expected only {LEGITIMATE_MASTER_IP}")

# ============================================================
# 3. DNP3 physical plausibility check
# ============================================================
def parse_link_frame(buf, offset):
    if offset + 10 > len(buf) or buf[offset] != 0x05 or buf[offset+1] != 0x64:
        return None
    length = buf[offset+2]
    if length < 5:
        return None
    user_data_len = length - 5
    pos = offset + 10
    remaining = user_data_len
    ud = bytearray()
    while remaining > 0:
        blen = min(16, remaining)
        if pos + blen + 2 > len(buf):
            return None
        ud.extend(buf[pos:pos+blen])
        pos += blen + 2
        remaining -= blen
    return {"total_len": pos - offset, "user_data": bytes(ud)}

def find_frames(buf):
    frames = []
    offset = 0
    while offset < len(buf) - 1:
        if buf[offset] == 0x05 and buf[offset+1] == 0x64:
            f = parse_link_frame(buf, offset)
            if f:
                frames.append(f)
                offset += f["total_len"]
                continue
        offset += 1
    return frames

def decode_g30v1(ud):
    found = []
    for i in range(len(ud) - 4):
        if (ud[i] == 0x1e and ud[i+1] == 0x01 and ud[i+2] == 0x00
                and ud[i+3] == 0x00 and ud[i+4] == 0x07):
            base = i + 5
            for idx in range(8):
                off = base + idx * 5
                if off + 5 > len(ud):
                    break
                if idx in ANALOG_LABELS:
                    val = struct.unpack("<i", ud[off+1:off+5])[0]
                    found.append((ANALOG_LABELS[idx], val))
    return found

last_values = {}

def check_dnp3(pkt):
    if not (pkt.haslayer(IP) and pkt.haslayer(TCP) and pkt.haslayer(Raw)):
        return
    if pkt[TCP].sport != DNP3_PORT and pkt[TCP].dport != DNP3_PORT:
        return
    raw = bytes(pkt[Raw].load)
    for frame in find_frames(raw):
        for tag, value in decode_g30v1(frame["user_data"]):
            limit = MAX_DELTA.get(tag)
            if tag in last_values and limit is not None:
                delta = abs(value - last_values[tag])
                if delta > limit:
                    alert("DNP3", f"{tag} changed by {delta} in one reading "
                                  f"({last_values[tag]} -> {value}) — exceeds plausible "
                                  f"limit of {limit}. Possible in-flight tampering.")
            last_values[tag] = value

def on_packet(pkt):
    check_modbus(pkt)
    check_dnp3(pkt)

# ============================================================
# main
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  Host-based IDS — ARP integrity / Modbus whitelist / DNP3 plausibility")
    print("=" * 60)
    print(f"  Monitoring peer   : {PEER_IP} (expect MAC {PEER_MAC})")
    print(f"  Legitimate master : {LEGITIMATE_MASTER_IP}")
    print(f"  Alert log         : {LOG_FILE}")
    print("=" * 60)

    t = threading.Thread(target=arp_monitor, daemon=True)
    t.start()

    try:
        sniff(iface=IFACE, filter=f"port {MODBUS_PORT} or port {DNP3_PORT}",
              prn=on_packet, store=False)
    except KeyboardInterrupt:
        print("\n[*] Stopped.")
    finally:
        logf.close()
