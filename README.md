# Substation Simulation — ICS/OT Security Lab

A self-contained Industrial Control System (ICS) simulation of an electrical
substation, built for security research and demonstration. It models a real
OT environment — a PLC driving a substation process, a SCADA master polling it
over DNP3, an MQTT telemetry pipeline, and an operator HMI — and ships with
attack tooling and hardening measures that demonstrate the security weaknesses
of unauthenticated industrial protocols (Modbus, DNP3).

The lab runs across two machines (VMs): **VM1** hosts the PLC and HMI layer,
**VM2** hosts the SCADA master and web frontend. Each is brought up with a
single Docker Compose command.

---

## Quick Start

### VM1 — PLC / HMI

```bash
git clone https://github.com/puck-ux/Substation-Simulation.git
cd Substation-Simulation/vm1
docker compose pull
docker compose up -d
```

That's the entire setup. The images are prebuilt with the PLC program, Node-RED
flows, and FUXA HMI project already configured — everything comes up running.

### VM2 — SCADA Master

```bash
git clone https://github.com/puck-ux/Substation-Simulation.git
cd Substation-Simulation/vm2
cp .env.example .env
# edit .env — set OPENPLC_IP to VM1's IP address
docker compose up -d
```

VM2 needs to know VM1's address. Set `OPENPLC_IP` in the `.env` file to
whatever IP VM1 has on your network, then bring it up.

---

## Access Points

Once VM1 is running, make sure to click start plc on both OpenPLCs:

| Interface         | URL                    | Login                                            |
|-------------------|------------------------|--------------------------------------------------|
| OpenPLC (primary) | http://localhost:8080  | openplc / openplc                                |
| OpenPLC (backup)  | http://localhost:8082  | openplc / openplc — open in an incognito tab     |
| Node-RED          | http://localhost:1880  | —                                                |
| FUXA HMI          | http://localhost:1881  | —                                                |

Once VM2 is running:

| Interface        | URL                        |
|------------------|----------------------------|
| DNP3 web frontend| http://localhost:5000      |
| Tag API (JSON)   | http://localhost:5001/tags |

---

## Architecture

```
  VM1 — Substation-PLC                       VM2 — Substation-DNP3
 ┌──────────────────────────┐               ┌────────────────────────┐
 │  OpenPLC (outstation)    │◄───DNP3 :20000─┤  dnp3master (SCADA)    │
 │  OpenPLC backup          │◄───Modbus :502─┤                        │
 │  Node-RED (Modbus→MQTT)  │               │  dnp3web (frontend)     │
 │  Mosquitto (MQTT broker) │               └────────────────────────┘
 │  FUXA (HMI)              │
 └──────────────────────────┘
        bridged LAN ───────────────────────────────┘
```

- **OpenPLC** runs the substation control logic as a DNP3 outstation and Modbus
  server. A backup PLC provides failover.
- **Node-RED** bridges Modbus data to MQTT.
- **Mosquitto** is the MQTT broker feeding the HMI.
- **FUXA** is the operator HMI dashboard.
- **dnp3master** (VM2) polls the PLC over DNP3 and exposes the tags via a web
  frontend and JSON API.

### Process points

| Tag                | Type            | Address         |
|--------------------|-----------------|-----------------|
| Substation Switch  | Coil (BOS)      | %QX0.0 / coil 0 |
| Substation Pipe    | Binary input    | %IX0.0          |
| Gauge              | Analog input    | %IW1            |
| Bus1 Voltage       | Analog input    | idx 2           |
| Feeder Current     | Analog input    | idx 3           |
| T1 Winding Temp    | Analog input    | idx 4           |
| Breaker Op Count   | Analog input    | idx 5           |
| T1 Temp Alarm      | Binary input    | idx 1           |

---

## Attacks

The `attacks/` folder contains proof-of-concept tooling demonstrating the
security weaknesses of unauthenticated ICS protocols. **For use only against
this isolated lab.**

| Script              | Attack                          | CIA impact        |
|---------------------|---------------------------------|-------------------|
| `ucw.py`            | Unauthenticated coil write      | Integrity/Control |
| `dos_flood.py`      | Modbus connection flood         | Availability      |
| `arp_spoof.py`      | ARP cache poisoning (MITM)      | Availability/enabler |
| `dnp3_tamper.py`    | DNP3 false-data injection       | Integrity         |
| `breaker_override.py`| Sustained breaker override     | Availability/Control|

Each demonstrates a real ICS attack pattern. The DNP3 tampering and breaker
override reproduce the class of manipulation seen in the CRASHOVERRIDE /
Industroyer grid attack.

---

## Defences

The `defences/` folder contains the hardening measures, each defeating specific
attacks above:

- **IP filtering** (`harden_vm1.sh`) — restricts Modbus port 502 to the
  legitimate master's IP via the Docker `DOCKER-USER` iptables chain. Defeats
  the unauthenticated coil write and breaker override.
- **Static ARP entries** — pins each host's peer to its known-good MAC,
  defeating ARP spoofing and, by extension, the DNP3 tampering that depends on
  the MITM position.
- **IDS monitor** (`ids_monitor.py`) — detects ARP MAC changes, unauthorized
  Modbus writes, and physically implausible value jumps.
- **TLS tunnel** (stunnel) — wraps DNP3 traffic in mutually-authenticated TLS,
  making it unreadable and unforgeable on the wire regardless of network
  position. The strongest mitigation.

Each defence's limitations are documented — IP filtering is spoofable, static
ARP is a host-level control that does not survive reboot, and both are
superseded by the cryptographic guarantees of the TLS tunnel.

---

## Requirements

- Docker and Docker Compose
- Two hosts (physical or VM) on the same network for the full two-VM setup;
  VM1 alone runs the complete PLC/HMI stack
- For the attacks: a third host on the same L2 segment (the attacker box)

## Notes

- This is a **simulation for research and education**. The attacks demonstrate
  why the security controls exist; run them only against this lab.
- The PLC program is compiled and baked into the prebuilt image. If OpenPLC
  comes up without the program loaded, re-upload `plc.st` via the web UI and
  set it to start in RUN mode.
- Windows users hitting a certificate-revocation error on download can add
  `--ssl-no-revoke` to curl, or use `git clone`.
