# VM Setup Guide for PLANET Hacker Capstone Project

## Overview
This guide will help you set up the virtual machine environment needed to run PLANET Hacker baseline tests on your Windows PC.

**Environment:**
- Host OS: Windows
- Hypervisor: VirtualBox
- VM 1: Kali Linux (attacker, 1.5GB RAM)
- VM 2: Metasploitable 2 (target, 512MB RAM)

---

## Step 1: Install VirtualBox

### Download VirtualBox
1. Go to: https://www.virtualbox.org/wiki/Downloads
2. Download **VirtualBox 7.0.x for Windows hosts**
3. Also download the **VirtualBox Extension Pack** (same page)

### Install VirtualBox
1. Run the installer (VirtualBox-x.x.x-Win.exe)
2. Follow default installation steps
3. After installation, double-click the Extension Pack file to install it
4. Restart your computer if prompted

---

## Step 2: Download Virtual Machines

### 2.1 Download Kali Linux VM

**Official Pre-built VM (Recommended):**
1. Go to: https://www.kali.org/get-kali/#kali-virtual-machines
2. Download: **Kali Linux VirtualBox 64-Bit (OVA)**
   - File size: ~3.5GB
   - Format: `.ova` file (can be directly imported)

**Credentials:**
- Username: `kali`
- Password: `kali`

### 2.2 Download Metasploitable 2 VM

**Official Download:**
1. Go to: https://sourceforge.net/projects/metasploitable/files/Metasploitable2/
2. Download: **metasploitable-linux-2.0.0.zip**
   - File size: ~800MB
   - Extract the ZIP file to a folder (e.g., `C:\VMs\Metasploitable2\`)

**Credentials:**
- Username: `msfadmin`
- Password: `msfadmin`

---

## Step 3: Import VMs into VirtualBox

### 3.1 Import Kali Linux

1. Open VirtualBox
2. Click **File → Import Appliance**
3. Browse to the Kali `.ova` file you downloaded
4. Click **Next**
5. Review settings:
   - Name: `Kali-Linux`
   - RAM: **1536 MB (1.5GB)** or more
   - CPUs: 2 (if available)
6. Click **Import**
7. Wait for import to complete (~5 minutes)

### 3.2 Import Metasploitable 2

1. In VirtualBox, click **New**
2. Configure:
   - **Name:** `Metasploitable2`
   - **Type:** Linux
   - **Version:** Ubuntu (64-bit) or Other Linux (64-bit)
   - **RAM:** 512 MB
   - Click **Next**
3. For Hard Disk:
   - Select **Use an existing virtual hard disk file**
   - Click the folder icon
   - Click **Add**
   - Browse to the extracted Metasploitable folder
   - Select `Metasploitable.vmdk`
   - Click **Choose**
4. Click **Create**

---

## Step 4: Configure VM Network Settings

**Critical:** Both VMs must be on the same network to communicate.

### Network Configuration Option 1: Host-Only Network (Recommended for Testing)

This isolates your VMs from the internet and your main network (safer for pentesting).

#### Create Host-Only Network:
1. In VirtualBox main window, go to **File → Tools → Network Manager**
2. Click the **Host-only Networks** tab
3. If no network exists, click **Create**
   - A network like `VirtualBox Host-Only Ethernet Adapter` will appear
   - Note the IPv4 Address (e.g., `192.168.56.1`)
   - DHCP Server should be enabled

#### Configure Kali Linux Network:
1. Right-click **Kali-Linux** VM → **Settings**
2. Go to **Network** tab
3. **Adapter 1:**
   - Enable Network Adapter: ✓
   - Attached to: **Host-only Adapter**
   - Name: Select the host-only network you created
4. Click **OK**

#### Configure Metasploitable 2 Network:
1. Right-click **Metasploitable2** VM → **Settings**
2. Go to **Network** tab
3. **Adapter 1:**
   - Enable Network Adapter: ✓
   - Attached to: **Host-only Adapter**
   - Name: Select the same host-only network
4. Click **OK**

### Network Configuration Option 2: Bridged Adapter (If you need internet access)

**Use this if your LLM needs internet access or if host-only doesn't work.**

#### Configure Both VMs:
1. For each VM (Kali and Metasploitable):
   - Right-click VM → **Settings** → **Network**
   - **Adapter 1:**
     - Enable Network Adapter: ✓
     - Attached to: **Bridged Adapter**
     - Name: Select your PC's active network adapter (Wi-Fi or Ethernet)
   - Click **OK**

**Note:** Bridged mode puts VMs on your actual network. Be careful not to scan beyond your VMs.

---

## Step 5: Start VMs and Get IP Addresses

### 5.1 Start Metasploitable 2

1. Select **Metasploitable2** VM
2. Click **Start**
3. Wait for boot (text-based interface)
4. Login:
   - Username: `msfadmin`
   - Password: `msfadmin`

### 5.2 Get Metasploitable 2 IP Address

In the Metasploitable terminal:
```bash
ifconfig
```

Look for `eth0` interface and note the `inet addr`:
```
eth0      Link encap:Ethernet  HWaddr 08:00:27:xx:xx:xx
          inet addr:192.168.56.101  Bcast:192.168.56.255  Mask:255.255.255.0
```

**Save this IP address** - you'll need it for PLANET Hacker configuration.

### 5.3 Start Kali Linux

1. Select **Kali-Linux** VM
2. Click **Start**
3. Wait for boot (GUI will load)
4. Login:
   - Username: `kali`
   - Password: `kali`

### 5.4 Get Kali Linux IP Address

Open terminal in Kali and run:
```bash
ip addr show
```

Look for the IP address on `eth0`:
```
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP
    inet 192.168.56.102/24 brd 192.168.56.255 scope global eth0
```

**Save this IP address** - you'll need it for SSH configuration.

---

## Step 6: Test VM Connectivity

### 6.1 Test from Kali to Metasploitable

In Kali terminal:
```bash
ping -c 4 <METASPLOITABLE_IP>
# Example: ping -c 4 192.168.56.101
```

You should see replies. If not, check:
- Both VMs are on same network type (both Host-only or both Bridged)
- VMs are running
- Firewalls are not blocking (unlikely in these VMs)

### 6.2 Test SSH to Metasploitable

From Kali terminal:
```bash
ssh msfadmin@<METASPLOITABLE_IP>
# Example: ssh msfadmin@192.168.56.101
```

- Password: `msfadmin`
- Type `yes` if asked about fingerprint
- You should get a shell on Metasploitable
- Type `exit` to disconnect

---

## Step 7: Configure SSH Access from Windows to Kali

PLANET Hacker runs on your Windows PC and needs SSH access to Kali.

### 7.1 Enable SSH on Kali

In Kali terminal:
```bash
# Start SSH service
sudo systemctl start ssh

# Enable SSH to start on boot
sudo systemctl enable ssh

# Verify SSH is running
sudo systemctl status ssh
```

### 7.2 Test SSH from Windows to Kali

On your Windows PC:

**Option 1: Using PowerShell/CMD**
```powershell
ssh kali@<KALI_IP>
# Example: ssh kali@192.168.56.102
```

**Option 2: Using PuTTY (if SSH not available)**
1. Download PuTTY: https://www.putty.org/
2. Run PuTTY
3. Enter Kali IP address
4. Port: 22
5. Click Open
6. Login as `kali` / `kali`

### 7.3 Set Up SSH Key (Optional but Recommended)

This allows PLANET Hacker to connect without password prompts.

On Windows PowerShell:
```powershell
# Generate SSH key (if you don't have one)
ssh-keygen -t rsa -b 4096

# Copy key to Kali
ssh-copy-id kali@<KALI_IP>
# Or manually: cat ~/.ssh/id_rsa.pub | ssh kali@<KALI_IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

Test passwordless login:
```powershell
ssh kali@<KALI_IP>
# Should connect without asking for password
```

---

## Step 8: Install MCP Server on Kali (Required for PLANET Hacker)

According to the README, you need MCP-Kali-Server running on Kali.

### 8.1 In Kali VM:

```bash
# Clone MCP Server
git clone https://github.com/Wh0am123/MCP-Kali-Server.git
cd MCP-Kali-Server

# Install dependencies
sudo apt update
sudo apt install python3-pip
pip3 install -r requirements.txt

# Start the server
python3 kali_server.py
```

The server should start and display a port number.

### 8.2 Note the server details:
- Kali IP: `<KALI_IP>`
- MCP Server Port: (shown in startup message, usually `3000` or similar)

---

## Step 9: Configure PLANET Hacker to Connect to VMs

### 9.1 Update Configuration Files

You'll need to update PLANET Hacker configuration to use:
1. **Kali SSH connection** - for executing Metasploit commands
2. **Metasploitable IP** - as the target for reconnaissance and attacks

Look for configuration in:
- `agents/config/settings.py`
- `.env` file
- MCP configuration files in `config_files/`

Typical values to set:
```env
KALI_HOST=192.168.56.102
KALI_USER=kali
KALI_PASSWORD=kali  # Or use SSH key
TARGET_HOST=192.168.56.101
MCP_SERVER_URL=http://192.168.56.102:3000
```

---

## Summary Checklist

- [ ] VirtualBox installed
- [ ] Kali Linux VM imported and started
- [ ] Metasploitable 2 VM imported and started
- [ ] Both VMs on same network (Host-only or Bridged)
- [ ] Metasploitable IP obtained: `______________`
- [ ] Kali IP obtained: `______________`
- [ ] Ping test Kali → Metasploitable: ✓
- [ ] SSH test Kali → Metasploitable: ✓
- [ ] SSH enabled on Kali
- [ ] SSH test Windows → Kali: ✓
- [ ] MCP Server running on Kali
- [ ] PLANET Hacker configuration updated with IP addresses

---

## Troubleshooting

### VMs can't ping each other
1. Check both VMs are using the same network adapter type
2. Check VMs are powered on
3. Run `ip addr show` on both to verify they're on same subnet
4. Try restarting VMs

### Can't SSH to Kali from Windows
1. Verify SSH is running: `sudo systemctl status ssh`
2. Check Windows firewall isn't blocking SSH
3. Verify you're using correct IP address
4. Try from Kali to itself first: `ssh kali@localhost`

### Metasploitable doesn't get an IP
1. Wait 30 seconds after boot
2. Run `sudo dhclient eth0` to request IP
3. Check VirtualBox DHCP server is enabled (File → Tools → Network Manager)

### Host-only network issues
1. In VirtualBox: File → Tools → Network Manager
2. Verify DHCP Server is enabled
3. Note the IP range (e.g., 192.168.56.0/24)
4. Both VMs should get IPs in this range

---

## Next Steps

Once VMs are set up and communicating:
1. Run baseline test of PLANET Hacker
2. Understand the output structure
3. Implement your failure classifier

Good luck with your capstone project!
