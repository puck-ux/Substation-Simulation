#!/bin/bash
#
# Static ARP hardening — defeats ARP spoofing (ARP_Spoof.py) and, by
# extension, the DNP3 tampering that relies on the MITM position.
#
# Pins each host's peer to its known-good MAC address so forged ARP
# replies are ignored and the attacker cannot insert itself into the path.
#
# MUST be run on BOTH VM1 and VM2 — pinning only one side leaves the
# other's cache poisonable and the attack still works.
#
#   sudo bash set_static_arp.sh
#
# IMPORTANT: run this with the ARP spoof STOPPED, so you capture the real
# MAC addresses and not the attacker's. The entries do NOT survive a reboot.

# ------------------------------------------------------------------
# CONFIG — set for the machine you are running this ON.
# On VM1, set PEER to VM2's IP/MAC. On VM2, set PEER to VM1's IP/MAC.
# ------------------------------------------------------------------
PEER_IP="192.168.68.111"        # the OTHER VM's IP
PEER_MAC="08:00:27:04:e1:8b"    # the OTHER VM's real MAC
IFACE="enp0s3"

echo "[*] Pinning static ARP entry: $PEER_IP -> $PEER_MAC on $IFACE"
sudo ip neigh replace "$PEER_IP" lladdr "$PEER_MAC" dev "$IFACE" nud permanent

echo "[*] Done. Verify with:  ip neigh show $PEER_IP   (should say PERMANENT)"
echo
echo "Remember to run this on the OTHER VM too, with its PEER set to this one."
echo
echo "To undo:"
echo "  sudo ip neigh del $PEER_IP dev $IFACE"
