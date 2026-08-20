import sys
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException
from config import VM1_IP

OPENPLC_IP = VM1_IP
PORT = 502
TIMEOUT = 5  # seconds before giving up

client = ModbusTcpClient(OPENPLC_IP, port=PORT, timeout=TIMEOUT)

try:
    if not client.connect():
        print(f"[BLOCKED] Could not connect to {OPENPLC_IP}:{PORT} — coil write blocked")
        sys.exit(1)

    # Read current state first
    current = client.read_coils(0, count=1, device_id=1)
    if current.isError():
        print(f"[BLOCKED] Coil write blocked — read failed: {current}")
        sys.exit(1)

    print(f"Current switch state: {current.bits[0]}")

    # Flip it to opposite
    new_val = not current.bits[0]
    result = client.write_coil(0, new_val, device_id=1)
    if result.isError():
        print(f"[BLOCKED] Coil write blocked: {result}")
    else:
        print(f"Wrote switch to: {new_val} — result: {result}")

except ConnectionException:
    print(f"[BLOCKED] Could not connect to {OPENPLC_IP}:{PORT} — coil write blocked")
except Exception as e:
    print(f"[BLOCKED] Coil write blocked — unexpected error: {e}")
finally:
    client.close()