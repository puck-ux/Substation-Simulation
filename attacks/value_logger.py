from scapy.all import sniff, IP, TCP, Raw
from datetime import datetime
import struct
import csv
import os
from config import VM1_IP

TARGET_IP = VM1_IP   # VM1 — OpenPLC
CSV_FILE  = "captured_values.csv"

ANALOG_LABELS = {
    1: "Gauge",
    2: "Bus1_Voltage_kV",
    3: "FeederCurrent_A",
    4: "T1_WindingTemp_C",
    5: "Breaker_OpCount",
}

# ---------------- CSV setup ----------------
new_file = not os.path.exists(CSV_FILE)
csv_fh = open(CSV_FILE, "a", newline="")
csv_writer = csv.writer(csv_fh)
if new_file:
    csv_writer.writerow(["timestamp", "source", "tag", "value", "note"])
    csv_fh.flush()

# latest known value of each tag, for the live snapshot
current = {label: None for label in ANALOG_LABELS.values()}
current["Substation_Switch"] = None

def record(tag, value, note=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    csv_writer.writerow([ts, "DNP3/Modbus wire (VM3 MITM)", tag, value, note])
    csv_fh.flush()
    current[tag] = value

def print_snapshot():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] --- current known substation state (captured passively) ---")
    for tag, val in current.items():
        print(f"    {tag:20s} = {val}")

# ---------------- DNP3 link layer (proven parser, unchanged) ----------------
def parse_link_frame(buf: bytes, offset: int):
    if offset + 10 > len(buf) or buf[offset] != 0x05 or buf[offset+1] != 0x64:
        return None
    length = buf[offset+2]
    if length < 5:
        return None
    user_data_len = length - 5
    pos = offset + 10
    remaining = user_data_len
    user_data = bytearray()
    while remaining > 0:
        blen = min(16, remaining)
        if pos + blen + 2 > len(buf):
            return None
        user_data.extend(buf[pos:pos+blen])
        pos += blen + 2
        remaining -= blen
    return {"total_len": pos - offset, "user_data": bytes(user_data)}

def find_frames(buf: bytes):
    frames = []
    offset = 0
    while offset < len(buf) - 1:
        if buf[offset] == 0x05 and buf[offset+1] == 0x64:
            frame = parse_link_frame(buf, offset)
            if frame:
                frames.append(frame)
                offset += frame["total_len"]
                continue
        offset += 1
    return frames

def decode_g30v1(ud: bytes):
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
                    value = struct.unpack("<i", ud[off+1:off+5])[0]
                    found.append((ANALOG_LABELS[idx], value))
    return found

def handle_dnp3(raw: bytes):
    updated = False
    for frame in find_frames(raw):
        points = decode_g30v1(frame["user_data"])
        for tag, value in points:
            if current.get(tag) != value:
                record(tag, value)
                updated = True
    if updated:
        print_snapshot()

# ---------------- Modbus (coil writes = control commands) ----------------
def handle_modbus(raw: bytes):
    if len(raw) < 12:
        return
    proto = struct.unpack(">H", raw[2:4])[0]
    if proto != 0:
        return
    func = raw[7]
    if func == 0x05:  # Write Single Coil
        addr = struct.unpack(">H", raw[8:10])[0]
        val = struct.unpack(">H", raw[10:12])[0]
        state = "ON" if val == 0xFF00 else "OFF"
        if addr == 0:
            record("Substation_Switch", state, note="Modbus coil write (control command)")
            print_snapshot()

# ---------------- packet handler ----------------
def on_packet(pkt):
    if not (pkt.haslayer(IP) and pkt.haslayer(TCP) and pkt.haslayer(Raw)):
        return
    if TARGET_IP not in (pkt[IP].src, pkt[IP].dst):
        return
    raw = bytes(pkt[Raw].load)
    if pkt[TCP].sport == 20000 or pkt[TCP].dport == 20000:
        handle_dnp3(raw)
    elif pkt[TCP].sport == 502 or pkt[TCP].dport == 502:
        handle_modbus(raw)

print(f"[*] Value logger started. Watching {TARGET_IP} (DNP3:20000, Modbus:502).")
print(f"[*] Recording changes to {CSV_FILE} — Ctrl+C to stop.\n")
try:
    sniff(filter=f"host {TARGET_IP} and (port 20000 or port 502)", prn=on_packet, store=False)
except KeyboardInterrupt:
    print("\n[*] Stopped.")
finally:
    csv_fh.close()
