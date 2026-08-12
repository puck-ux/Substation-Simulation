import time
import os
import sys
import logging
import threading
from flask import Flask, jsonify, request
from pydnp3 import opendnp3, openpal, asiopal, asiodnp3
from pymodbus.client import ModbusTcpClient

devnull_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull_fd, 1)
os.close(devnull_fd)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    stream=sys.stderr
)
log = logging.getLogger(__name__)

OPENPLC_IP      = "10.80.129.6"
DNP3_PORT       = 20000
MODBUS_PORT     = 502
MASTER_ADDR     = 1
OUTSTATION_ADDR = 10
API_PORT        = 5001
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "5"))

dnp3_tags = {
    "gauge":  "ERR",
    "pipe":   "ERR",
    "switch": "ERR",
    "t1_temp_alarm":  "ERR",
    "bus1_voltage":   "ERR",
    "feeder_current": "ERR",
    "t1_winding_temp": "ERR",
    "breaker_opcount": "ERR",
}
dnp3_lock = threading.Lock()

flask_app = Flask(__name__)

@flask_app.route('/tags')
def get_tags():
    with dnp3_lock:
        return jsonify(dict(dnp3_tags))

@flask_app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@flask_app.route('/control', methods=['POST'])
def control():
    data = request.json
    action = data.get('action', '').strip()
    if action not in ('on', 'off'):
        return jsonify({'success': False, 'error': 'Invalid action'})
    result = set_switch(action == 'on')
    return jsonify({'success': result})

def run_flask():
    import logging as pylog
    pylog.getLogger('werkzeug').setLevel(pylog.ERROR)
    flask_app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)

class TagSOEHandler(opendnp3.ISOEHandler):
    def __init__(self):
        super().__init__()
        self.last_update = {}

    def Process(self, info, values):
        def handle_value(val):
            index = val.index
            wrapper = val.value
            type_name = type(wrapper).__name__
            with dnp3_lock:
                if type_name == "Binary" and index == 0:
                    dnp3_tags["pipe"] = "ON" if wrapper.value else "OFF"
                elif type_name == "Binary" and index == 1:
                    dnp3_tags["t1_temp_alarm"] = "ON" if wrapper.value else "OFF"
                elif type_name == "BinaryOutputStatus" and index == 0:
                    dnp3_tags["switch"] = "ON" if wrapper.value else "OFF"
                elif type_name == "Analog" and index == 1:
                    dnp3_tags["gauge"] = int(wrapper.value)
                elif type_name == "Analog" and index == 2:
                    dnp3_tags["bus1_voltage"] = int(wrapper.value)
                elif type_name == "Analog" and index == 3:
                    dnp3_tags["feeder_current"] = int(wrapper.value)
                elif type_name == "Analog" and index == 4:
                    dnp3_tags["t1_winding_temp"] = int(wrapper.value)
                elif type_name == "Analog" and index == 5:
                    dnp3_tags["breaker_opcount"] = int(wrapper.value)
                else:
                    log.debug(f"[SOE] Unhandled point: type={type_name} index={index} value={getattr(wrapper, 'value', None)}")

        values.ForeachItem(handle_value)

    def Start(self):
        pass

    def End(self):
        pass

def get_modbus_client():
    client = ModbusTcpClient(OPENPLC_IP, port=MODBUS_PORT)
    client.connect()
    return client

def modbus_write_coil(client, address, value):
    """Works whether this pymodbus install expects device_id= (newer) or slave= (older)."""
    try:
        return client.write_coil(address, value, device_id=1)
    except TypeError:
        return client.write_coil(address, value, slave=1)

def set_switch(activate):
    client = get_modbus_client()
    try:
        result = modbus_write_coil(client, 0, activate)
        if result.isError():
            log.error(f"[CONTROL] Modbus write failed: {result}")
            return False
        action = "ON" if activate else "OFF"
        log.info(f"[CONTROL] Switch set {action} via Modbus coil write")
        return True
    except Exception as e:
        log.error(f"[CONTROL] Exception: {type(e).__name__}: {e}")
        return False
    finally:
        client.close()

def print_tags(tags):
    print(f"{'─'*46}",                                           file=sys.stderr)
    print(f"  DNP3 Tag Monitor  [{OPENPLC_IP}]",                file=sys.stderr)
    print(f"{'─'*46}",                                           file=sys.stderr)
    print(f"  Gauge Random      (AI  idx 1) : {tags['gauge']}",  file=sys.stderr)
    print(f"  Substation Pipe   (BI  idx 0) : {tags['pipe']}",   file=sys.stderr)
    print(f"  Substation Switch (BOS idx 0) : {tags['switch']}", file=sys.stderr)
    print(f"  T1 Temp Alarm     (BI  idx 1) : {tags['t1_temp_alarm']}", file=sys.stderr)
    print(f"  Bus1 Voltage      (AI  idx 2) : {tags['bus1_voltage']}", file=sys.stderr)
    print(f"  Feeder Current    (AI  idx 3) : {tags['feeder_current']}", file=sys.stderr)
    print(f"  T1 Winding Temp   (AI  idx 4) : {tags['t1_winding_temp']}", file=sys.stderr)
    print(f"  Breaker OpCount   (AI  idx 5) : {tags['breaker_opcount']}", file=sys.stderr)
    print(f"{'─'*46}",                                           file=sys.stderr)

def print_menu():
    print(f"\n{'═'*46}",                    file=sys.stderr)
    print(f"  SCADA Control Console",       file=sys.stderr)
    print(f"{'─'*46}",                      file=sys.stderr)
    print(f"  1  →  Substation Switch ON",  file=sys.stderr)
    print(f"  2  →  Substation Switch OFF", file=sys.stderr)
    print(f"  3  →  Poll tags (DNP3)",      file=sys.stderr)
    print(f"  q  →  Quit",                  file=sys.stderr)
    print(f"{'═'*46}",                      file=sys.stderr)

def command_loop(master):
    time.sleep(3)
    log.info("Requesting integrity poll from outstation...")
    time.sleep(2)

    print(f"\n  Initial DNP3 tag values:", file=sys.stderr)
    print_tags(get_dnp3_tags_local())

    if not sys.stdin.isatty():
        log.info("No interactive terminal attached (running detached/-d) — skipping menu, running as background service.")
        log.info("Control is available via the Flask API on /control instead.")
        while True:
            time.sleep(3600)

    while True:
        print_menu()
        try:
            cmd = input("Command: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            log.info("Shutting down...")
            os._exit(0)

        if cmd == "1":
            log.info("[CONTROL] Setting Switch ON...")
            set_switch(True)
            time.sleep(2)
            print(f"\n  Updated values:", file=sys.stderr)
            print_tags(get_dnp3_tags_local())

        elif cmd == "2":
            log.info("[CONTROL] Setting Switch OFF...")
            set_switch(False)
            time.sleep(2)
            print(f"\n  Updated values:", file=sys.stderr)
            print_tags(get_dnp3_tags_local())

        elif cmd == "3":
            try:
                duration_str = input("Poll duration (seconds): ").strip()
                duration = int(duration_str)
            except (ValueError, EOFError):
                log.warning("Invalid duration — enter a number")
                continue

            log.info(f"[POLL] Polling every 5s for {duration}s via DNP3...")
            end_time = time.time() + duration
            while time.time() < end_time:
                remaining = int(end_time - time.time())
                time.sleep(2)
                print(f"\n  [{remaining}s remaining]", file=sys.stderr)
                print_tags(get_dnp3_tags_local())
                time.sleep(3)
            log.info("[POLL] Poll complete — returning to menu")

        elif cmd == "q":
            log.info("Exiting.")
            os._exit(0)

        elif cmd == "":
            pass

        else:
            log.warning(f"Unknown command: '{cmd}'")

def get_dnp3_tags_local():
    with dnp3_lock:
        return dict(dnp3_tags)

def main():
    log.info("═" * 46)
    log.info("  DNP3 SCADA Master starting...")
    log.info(f"  Outstation : {OPENPLC_IP}:{DNP3_PORT}")
    log.info(f"  Master addr: {MASTER_ADDR}  Outstation addr: {OUTSTATION_ADDR}")
    log.info(f"  Scan interval: {SCAN_INTERVAL_SECONDS}s")
    log.info(f"  Tag API    : http://0.0.0.0:{API_PORT}/tags")
    log.info("═" * 46)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log.info(f"Tag API running on port {API_PORT}")

    manager = asiodnp3.DNP3Manager(1, asiodnp3.ConsoleLogger().Create())

    channel = manager.AddTCPClient(
        "client",
        opendnp3.levels.NOTHING,
        asiopal.ChannelRetry().Default(),
        OPENPLC_IP,
        "0.0.0.0",
        DNP3_PORT,
        asiodnp3.PrintingChannelListener().Create()
    )

    config = asiodnp3.MasterStackConfig()
    config.master.responseTimeout = openpal.TimeDuration().Seconds(5)
    config.link.LocalAddr  = MASTER_ADDR
    config.link.RemoteAddr = OUTSTATION_ADDR

    soe_handler = TagSOEHandler()

    master = channel.AddMaster(
        "master",
        soe_handler,
        asiodnp3.DefaultMasterApplication().Create(),
        config
    )

    master.AddClassScan(
        opendnp3.ClassField().AllClasses(),
        openpal.TimeDuration().Seconds(SCAN_INTERVAL_SECONDS)
    )

    master.Enable()
    log.info("DNP3 master enabled — connecting to outstation...")

    command_loop(master)

if __name__ == "__main__":
    main()
