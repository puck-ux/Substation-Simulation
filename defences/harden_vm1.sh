#!/bin/bash
#
# Substation PLC hardening — IP filtering for Modbus.
#
# Run ON VM1 (the OpenPLC host). Restricts the Modbus port (502) so only the
# legitimate SCADA master (VM2) may connect. Blocks the attacker's direct
# coil writes (Unauthenticated_Coil_Write.py and breaker_override.py) while
# leaving legitimate control from VM2 working.
#
#   sudo bash harden_vm1.sh
#
# NOTE: OpenPLC runs in a Docker container, so the rule must go in the
# DOCKER-USER chain, NOT INPUT. Container-bound traffic traverses Docker's
# forwarding chains and never hits INPUT — an INPUT rule would silently do
# nothing (the DROP counter stays at zero while the attack still works).

set -e

# ------------------------------------------------------------------
# CONFIG — set to the real values on your network
# ------------------------------------------------------------------
VM2_IP="192.168.68.111"    # legitimate SCADA master (dnp3master host)
MODBUS_PORT=502

echo "[*] Hardening VM1 — restricting Modbus port $MODBUS_PORT to $VM2_IP"

# allow the legitimate master
sudo iptables -C DOCKER-USER -p tcp -s "$VM2_IP" --dport "$MODBUS_PORT" -j ACCEPT 2>/dev/null \
  || sudo iptables -I DOCKER-USER -p tcp -s "$VM2_IP" --dport "$MODBUS_PORT" -j ACCEPT

# drop everyone else hitting Modbus (this catches the attacker's writes)
sudo iptables -C DOCKER-USER -p tcp --dport "$MODBUS_PORT" -j DROP 2>/dev/null \
  || sudo iptables -A DOCKER-USER -p tcp --dport "$MODBUS_PORT" -j DROP

echo "[*] Done. Only $VM2_IP may issue Modbus reads/writes to the PLC."
echo "    Verify with:  sudo iptables -L DOCKER-USER -n -v"
echo "    (run an attack from VM3 — the DROP counter should increment)"
echo
echo "To undo:"
echo "  sudo iptables -D DOCKER-USER -p tcp --dport $MODBUS_PORT -j DROP"
echo "  sudo iptables -D DOCKER-USER -p tcp -s $VM2_IP --dport $MODBUS_PORT -j ACCEPT"
