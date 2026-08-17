from flask import Flask, request, jsonify
from flask_cors import CORS
from pymodbus.client import ModbusTcpClient
import requests

app = Flask(__name__)
CORS(app)

MODBUS_PORT = 502
BACKUP_PORT = 504
DNP3MASTER_URL = "http://dnp3master:5001"   # docker inspect dnp3master | grep IPAddress


def get_client(ip, portinput):
    client = ModbusTcpClient(ip, port=portinput)
    if not client.connect():
        return None
    return client


def modbus_read_coils(client, address, count=1):
    """Works whether this pymodbus install expects device_id= (newer) or slave= (older)."""
    try:
        return client.read_coils(address, count=count, device_id=1)
    except TypeError:
        return client.read_coils(address, count=count, slave=1)


def modbus_write_coil(client, address, value):
    """Same compatibility handling as modbus_read_coils, for writes."""
    try:
        return client.write_coil(address, value, device_id=1)
    except TypeError:
        return client.write_coil(address, value, slave=1)


@app.route('/api/connect', methods=['POST'])
def connect():
    data = request.json
    ip = data.get('ip', '').strip()
    if not ip:
        return jsonify({'success': False, 'error': 'No IP provided'})

    try:
        res = requests.get(f"{DNP3MASTER_URL}/health", timeout=2)
        if res.status_code == 200:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'dnp3master not responding'})
    except Exception:
        return jsonify({'success': False, 'error': 'Could not reach dnp3master'})


@app.route('/api/tags', methods=['GET'])
def get_tags():
    ip2 = request.args.get('ip2', '').strip()

    try:
        res = requests.get(f"{DNP3MASTER_URL}/tags", timeout=2)
        tags = res.json()
        result = {
            'gauge':  tags.get('gauge', 'ERR'),
            'pipe':   tags.get('pipe',  'ERR'),
            'switch': tags.get('switch','ERR'),
            'backup_active': 'ERR',
            't1_temp_alarm':   tags.get('t1_temp_alarm', 'ERR'),
            'bus1_voltage':    tags.get('bus1_voltage', 'ERR'),
            'feeder_current':  tags.get('feeder_current', 'ERR'),
            't1_winding_temp': tags.get('t1_winding_temp', 'ERR'),
            'breaker_opcount': tags.get('breaker_opcount', 'ERR'),
        }
    except Exception:
        result = {
            'gauge': 'ERR', 'pipe': 'ERR', 'switch': 'ERR', 'backup_active': 'ERR',
            't1_temp_alarm': 'ERR', 'bus1_voltage': 'ERR', 'feeder_current': 'ERR',
            't1_winding_temp': 'ERR', 'breaker_opcount': 'ERR',
            'error': 'Could not reach dnp3master'
        }

    if not ip2:
        result['backup_debug'] = "ip2 was empty/missing in the request"
    else:
        client2 = get_client(ip2, BACKUP_PORT)
        if client2:
            try:
                backup = modbus_read_coils(client2, 1, count=1)
                if backup.isError():
                    result['backup_active'] = 'ERR'
                    result['backup_debug'] = f"Modbus error response: {backup}"
                else:
                    result['backup_active'] = 'ON' if backup.bits[0] else 'OFF'
            except Exception as e:
                result['backup_active'] = 'ERR'
                result['backup_debug'] = f"{type(e).__name__}: {e}"
            finally:
                client2.close()
        else:
            result['backup_active'] = 'ERR'
            result['backup_debug'] = f"Could not open Modbus connection to {ip2}:{BACKUP_PORT}"

    return jsonify(result)


@app.route('/api/control', methods=['POST'])
def control():
    data = request.json
    ip     = data.get('ip', '').strip()
    ip2    = data.get('ip2', '').strip()
    action = data.get('action', '').strip()

    if not ip or action not in ('on', 'off'):
        return jsonify({'success': False, 'error': 'Invalid request'})

    try:
        res = requests.post(f"{DNP3MASTER_URL}/control",
                          json={'action': action}, timeout=2)
        master_result = res.json()
        if master_result.get('success'):
            return jsonify({'success': True})
    except Exception:
        pass

    if ip2:
        client2 = get_client(ip2, BACKUP_PORT)
        if client2:
            try:
                result = modbus_write_coil(client2, 0, action == 'on')
                if not result.isError():
                    return jsonify({'success': True, 'note': 'Sent to backup PLC 2'})
                return jsonify({'success': False, 'error': 'Modbus write failed on PLC 2'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
            finally:
                client2.close()

    return jsonify({'success': False, 'error': 'Could not connect to either PLC'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
