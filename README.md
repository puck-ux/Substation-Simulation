
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
## Virtual Machine Setup

### Note
If at any point you run into the error "is not valid yet" after saving the machine state and reloading it later just run these commands to reset the machine's time
```bash
sudo systemctl restart chronyd
sudo chronyc makestep
```

### Overview
This section covers deploying the substation simulation across two Red Hat
Enterprise Linux (RHEL) virtual machines running in VirtualBox. VM 1 hosts the
PLC and HMI stack, VM 2 hosts the SCADA master and web frontend.

### Prerequisites
Software required on the host machine:
- VirtualBox — https://www.virtualbox.org/wiki/Downloads
- RHEL 9 Boot ISO — https://developers.redhat.com/products/rhel/download

Accounts required:
- Red Hat Developer Account — https://developers.redhat.com (free, no license needed)

### Creating a Red Hat Developer Account
1. Go to https://developers.redhat.com and click Register
2. Fill in your details and verify your email
3. This gives free access to RHEL with a no-cost developer subscription

### Downloading the RHEL ISO
1. Log into your developer account at https://developers.redhat.com/products/rhel/download
2. Select Red Hat Enterprise Linux 9.6 (x86_64)
3. Download the Boot ISO (~800MB)

### Creating VM 1 — PLC/HMI
In VirtualBox click New and configure:
- Name: Substation-PLC
- ISO Image: Select the RHEL Boot ISO
- Username and Password: Whatever you want
- RAM: 4096MB
- CPU: 2 cores
- Disk: 20GB dynamically allocated
- Storage: Mount the RHEL Boot ISO

Open Settings > Network and set Attached to to Bridged Adapter.

### Installing RHEL on VM 1
1. Start the VM — it boots from the ISO into the RHEL installer
2. Select English and click Continue
3. At Installation Destination — click the virtual disk, leave Automatic selected, click Done (you might have to do this twice)
4. At Connect to Red Hat — enter your developer account credentials to activate the subscription
5. At Software Selection — select Server with GUI, click Done
6. At Network & Hostname — enable the network adapter, confirm it gets an IP
7. At Root Password — set a root password
8. At User Creation — create a user (e.g. your-name), tick Make this user administrator
9. Click Begin Installation and wait for it to complete
10. Click Reboot System when done
11. Complete initial setup

### Installing Docker on VM 1
Open a terminal and run:
```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```
Log out and back in, then verify:
```bash
docker --version
docker compose version
```
Install Git and the repository on the VM
```bash
sudo dnf install git
git clone https://github.com/puck-ux/Substation-Simulation.git
```
Power down the VM

### Creating VM 2 — DNP3 SCADA Master
1. Right click VM 1 and click "clone"
2. Rename it something like Substation-DNP3
3. Choose "Generate new MAC addresses for all network adapters" under MAC Address Policy
4. Click finish

---
## Quick Start
### VM1 — PLC / HMI
```bash
cd Substation-Simulation/vm1
docker compose pull
docker compose up -d
```
### Finding VM1's IP Address
VM2 needs VM1's IP address to connect to the PLC. On **VM1**, open a terminal and run:
```bash
ip addr show enp0s3
```
Look for the `inet` line — the address (e.g. `192.168.68.110`) is VM1's IP. With
a bridged adapter this is assigned by DHCP and can change when you reconnect or
switch networks; if VM2 stops connecting, re-check it here and update VM2's `.env`.

### VM2 — SCADA Master
```bash
# VM1 must already be running and reachable on the network.
sudo dnf install -y nodejs npm
cd Substation-Simulation/vm2
# Set VM1's IP
cp .env.example .env
nano .env                        # OPENPLC_IP=<VM1's IP>
# exit it with ctrl + x then y
# Backend (builds from source — first run takes a few minutes)
docker compose up -d --build
# Frontend (separate dev server on :3000)
cd dnp3web/dnp3frontend
npm install
npm start
```
VM2 needs to know VM1's address. Set `OPENPLC_IP` in the `.env` file to
whatever IP VM1 has on your network, then bring it up.

---
## Access Points
Once VM1 is running, the backup MUST be opened in an incognito tab and make sure to click start plc on both OpenPLCs:
| Interface        | URL                        | Login             |
|------------------|----------------------------|-------------------|
| OpenPLC (primary)| http://localhost:8080      | openplc / openplc |
| OpenPLC (backup) | http://localhost:8082      | openplc / openplc | 
| Node-RED         | http://localhost:1880      | —                 |
| FUXA HMI         | http://localhost:1881      | —                 |
Once VM2 is running:
| Interface        | URL                        |
|------------------|----------------------------|
| DNP3 web frontend| http://localhost:3000      |
| Tag API (JSON)   | http://localhost:3001/tags |
### PLC
![PLC](Screenshots/plc.PNG)

### NodeRed
![NodeRed](Screenshots/nodered.PNG)

### HMI
![HMI](Screenshots/HMI.PNG)

### Backup PLC
![backup_plc](Screenshots/backup_plc.PNG)

### DNP3 Master
![dnp3master](Screenshots/dnp3master.PNG)
---
## Architecture
```
  VM1 — Substation-PLC                        VM2 — Substation-DNP3
 ┌──────────────────────────┐                ┌────────────────────────┐
 │  OpenPLC (outstation)    │◄───DNP3 :20000─┤  dnp3master (SCADA)    │
 │  OpenPLC backup          │◄───Modbus :502─┤                        │
 │  Node-RED (Modbus→MQTT)  │                │  dnp3web (frontend)    │
 │  Mosquitto (MQTT broker) │                └────────────────────────┘
 │  FUXA (HMI)              │                      │
 └──────────────────────────┘                      │
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
# Attacks
For this we will create a third VM with Debian

## Attacker VM Setup (VM3 — Debian)

The attack scripts run from a third VM on the same network segment as VM1 and
VM2. This VM uses Debian and runs command-line only (no desktop).

### Creating VM 3 — Attacker

In VirtualBox click **New** and configure:

- **Name:** Attacker
- **ISO Image:** Debian 12 netinst ISO — [Download Here](https://cdimage.debian.org/cdimage/archive/12.12.0/amd64/iso-cd/debian-12.12.0-amd64-netinst.iso)
- Leave "Proceed with Unattended Installation" unchecked or you will download the desktop version!
- **RAM:** 2048MB
- **CPU:** 2 cores
- **Disk:** 20GB dynamically allocated
- **Network:** Bridged Adapter (must be on the same network as VM1 and VM2)

### Installing Debian

The Debian installer has more steps than RHEL. Work through the screens in order:

1. At the boot menu, select **Graphical Install**.
2. **Language / Location / Keyboard** — select your language, country, and keyboard layout.
3. **Network configuration:**
   - It auto-configures via DHCP over the bridged adapter.
   - **Hostname:** enter a name (e.g. `attacker`).
   - **Domain name:** leave blank and continue.
4. **Set up users and passwords:**
   - **Root password:** set a root password (the attacks run as root).
   - **Full name / username / password:** create your user account.
5. **Clock / Timezone** — select your timezone.
6. **Partition disks:**
   - Select **Guided - use entire disk**.
   - Choose the virtual disk.
   - Select **All files in one partition**.
   - Select **Finish partitioning and write changes to disk** → **Yes**.
7. **Package manager** — accept the default Debian mirror, leave the proxy blank.
8. **Software selection** — this screen has a checklist. Use the spacebar to
   toggle options:
   - **Untick** "Debian desktop environment" and all desktop options (GNOME, etc.).
   - **Leave ticked** "SSH server" and "standard system utilities".
   - This gives a minimal command-line install.
9. **GRUB bootloader** — install to the primary drive (usually `/dev/sda`) when prompted.
10. Wait for installation to complete, then **reboot** and remove the ISO.

After reboot you land at a command-line login. Log in with the user you created.

### Installing Dependencies

A minimal Debian install is missing most tools the scripts need. Install them:

```bash
su -                                    # switch to root (or use sudo if configured)
apt update
apt install -y python3 python3-pip git curl iptables tcpdump libpcap-dev
pip3 install scapy pymodbus --break-system-packages
```

> **Note:** Debian 12 requires the `--break-system-packages` flag for pip
> installs. It also ships with `nftables` rather than `iptables` by default —
> the `iptables` package above provides the `iptables` command the NFQUEUE-based
> scripts use. `dhclient` is not installed; renew DHCP leases with
> `sudo systemctl restart networking` or by bringing the interface down and up.

### Running the Attacks

Clone the repository and run the scripts as root (raw socket access requires it):

```bash
git clone https://github.com/puck-ux/Substation-Simulation.git
cd Substation-Simulation/attacks
sudo python3 arp_spoof.py
```

> **Note:** The attacker VM must be on the same L2 network segment as VM1 and
> VM2 (bridged to the same adapter) for ARP spoofing and MITM attacks to work.
> IP addresses are DHCP-assigned — check the target IPs with `ip addr` on each
> VM and update the scripts' target variables accordingly.

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
