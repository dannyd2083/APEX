# PLANTE — AI-Driven Automated Penetration Testing

An AI-powered automated penetration testing framework that uses LLM agents to conduct autonomous reconnaissance and exploitation against intentionally vulnerable systems.

We inherited this project from the 2025 cohort and have been extending it — see the Capstone section at the bottom for what changed and where it's going.

## Original Architecture (v1)

The original system is a single orchestrator that plans everything upfront and executes blindly:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Windows Host  │     │   Kali Linux    │     │ Metasploitable2 │
│                 │     │   (Attacker)    │     │    (Target)     │
│  ┌───────────┐  │     │                 │     │                 │
│  │Orchestrator│──┼────▶│ MCP-Kali-Server │────▶│  Vulnerable     │
│  └───────────┘  │ SSH │   (Flask API)   │     │   Services      │
│        │        │     │                 │     │                 │
│        ▼        │     └─────────────────┘     └─────────────────┘
│  ┌───────────┐  │
│  │ OpenRouter│  │
│  │   (LLM)   │  │
│  └───────────┘  │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │ Supabase  │  │
│  │ (Logging) │  │
│  └───────────┘  │
└─────────────────┘
```

Pipeline: `Recon → LLM plans all commands upfront → Execute → Classify failure → Remediate → Done`

## New Architecture (v2, in progress)

We're replacing the orchestrator with three agents that work in a closed loop — the coordinator sees command output before deciding what to do next, rather than planning everything at once:

```
┌──────────────────────────────────────────┐
│              Windows Host                │
│                                          │
│  ┌─────────────┐    ┌────────────────┐   │
│  │ Coordinator │───▶│  Recon Agent   │   │
│  │  (Brain)    │    │ nmap/gobuster  │   │
│  │             │◀───│ /ZAP/curl      │   │
│  │             │    └────────────────┘   │
│  │             │                         │
│  │             │    ┌────────────────┐   │
│  │             │───▶│ Execute Agent  │   │
│  │             │    │ curl/sqlmap    │   │
│  │             │◀───│ /web tools     │   │
│  └──────┬──────┘    └────────────────┘   │
│         ▼                                │
│  ┌─────────────┐   All agents use:       │
│  │  Supabase   │   Kali Linux VM via     │
│  │  (Logging)  │   MCP + SSH             │
│  └─────────────┘                         │
└──────────────────────────────────────────┘
```

Focus is now on **black-box web pentesting** — the coordinator reads HTTP responses, adapts its approach, and tracks findings in a task tree (PTT). This is what was missing in v1.

## Document Source
- [LangChain](https://docs.langchain.com/oss/python/langchain/overview)
- [MCP-Kali-Server](https://github.com/Wh0am123/MCP-Kali-Server)

## Setup

### 1. mcp-kali-server

MCP bridging Kali VM and Agents — [Github](https://github.com/Wh0am123/MCP-Kali-Server).

#### 1.1 Setting up on Kali VM

1. Download and import Kali VM from [official website](https://www.kali.org/get-kali/#kali-virtual-machines)
    - Extract zip to desired location
    - In VirtualBox, click **Add** to import VM
    - Change network setting to **Host-Only Adapter** (for Adapter 1)
    - Add **NAT** for Adapter 2 (for internet access)
    - Open VM, username/password: kali
2. In Kali VM, clone MCP Server
    ```
    git clone https://github.com/Wh0am123/MCP-Kali-Server.git
    ```
3. Start Server (**IMPORTANT: use --ip 0.0.0.0 to allow external connections**)
    ```
    python MCP-Kali-Server/kali_server.py --ip 0.0.0.0
    ```
4. For web recon, start OWASP ZAP in daemon mode:
    ```
    zaproxy -daemon -port 8080 -host 0.0.0.0
    ```

#### 1.2 Setting up on Host Machine

1. Clone the repo & install requirements
    ```
    git clone https://github.com/Wh0am123/MCP-Kali-Server.git
    cd MCP-Kali-Server
    python3 -m venv venv

    # For Mac or Linux
    source venv/bin/activate

    # For Windows
    .\venv\Scripts\activate.bat

    pip install requests fastmcp
    ```

2. Fix logging errors in `mcp_server.py` — change `sys.stdout` to `sys.stderr`:

    ```python
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )
    ```

3. Start server
    ```
    python kali_server.py
    ```

### 2. Project Installation
```
pip install -r requirements.txt
```

**Additional packages needed:**
```
pip install langchain-mcp-adapters asyncssh paramiko scp
```

### 3. Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
# VM IP Addresses (find yours with `ip addr` in each VM)
KALI_IP=<your-kali-ip>

# OpenRouter LLM
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Tester Name (for result files)
TESTER_NAME=YourName

# Supabase Database
DB_HOST=your-project.supabase.co
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your-password
DB_NAME=postgres
DB_SSLMODE=require
```

### 4. VirtualBox Network Setup

Each setup may have different IP addresses depending on your VirtualBox configuration.

1. Open VirtualBox > File > **Host Network Manager**
2. Create or select a Host-Only Network
3. Enable DHCP Server (or configure static IPs)
4. For each VM, go to Settings > Network:
   - **Adapter 1**: Host-Only Adapter (select your network)
   - **Adapter 2** (Kali only): NAT (for internet access)
5. Start VMs and find their IPs:
   ```bash
   ip addr
   ```
6. Update your `.env` file with the discovered IPs

**Note**: Common ranges are `192.168.56.x` or `192.168.x.x` depending on your Host-Only network configuration.

### 5. Database Migration (v2)

Run `docs/migration_v2.sql` in the Supabase SQL editor. Adds the tables needed for the multi-agent system (tasks, findings, hypotheses, gate_decisions). Safe to run — no destructive changes to existing tables.

## Repo Folders

### agents/
- `orchestrator.py` — original single-pipeline engine (v1, still works)
- `coordinator.py` — multi-agent brain (v2, in progress)
- `recon_agent.py` — recon worker (ZAP, gobuster, nmap)
- `state.py` — shared state dataclasses for v2
- `logger.py` — DB logging for both v1 and v2
- `tools/` — SSH and MCP tool wrappers
- `llms/` — OpenRouter client
- `prompts/` — LLM prompt templates

### docs/
- `migration_v2.sql` — database migration for v2 tables
- `run_log.md` — notes from all test runs
- `presentation_outline.md` — slides outline

### results/
Output JSON files from test runs (gitignored, local only).

## Running

### v1 (original pipeline, still works)

```bash
# Activate venv
.\venv\Scripts\activate    # Windows
source .venv/bin/activate  # Mac/Linux

python -m agents.orchestrator --target-ip <IP> --target-os <OS> --target-name <Name> --fresh-scan
```

### v2 (multi-agent, in progress)

Not ready yet — coordinator.py is being built.

## Troubleshooting

### Kali Server Not Accessible from Host

**Symptom**: `curl http://<kali-ip>:5000/health` fails from host machine

**Solution**: Start server with `--ip 0.0.0.0`:
```bash
python3 kali_server.py --ip 0.0.0.0
```

### Port 5000 Already in Use on Kali
```bash
sudo kill -9 $(sudo lsof -t -i :5000)
```

### SSH Permission Denied

**Symptom**: SSH fails despite correct password

**Solution**:
1. Verify correct IP (`ip addr` in VM console)
2. Check `/etc/ssh/sshd_config`:
   ```
   PasswordAuthentication yes
   KbdInteractiveAuthentication yes
   ```
3. Restart SSH: `sudo systemctl restart sshd`

### OpenRouter 402 Error

**Symptom**: `Error code: 402 - insufficient credits`

**Solution**:
1. Add credits at https://openrouter.ai/settings/credits
2. Or reduce `max_tokens` in `agents/llms/OpenRouter.py`

### Windows Filename Error

**Symptom**: `OSError: [Errno 22] Invalid argument` when saving results

**Solution**: Fixed in `agents/helpers/save_json.py` — colons replaced with dashes in timestamps

## Cost Estimates

- **OpenRouter (Grok-4)**: ~$0.20–0.50 per run (1 round), ~$1.00–1.40 (3 rounds)
- **Supabase**: Free tier is enough for testing
- **OWASP ZAP**: Free, runs on Kali

## Capstone 2026

We tested the v1 system on 7 HackTheBox machines:

| Box | OS | Result |
|-----|----|--------|
| Lame | Linux | Samba exploit worked |
| Blue | Windows | EternalBlue worked |
| Legacy | Windows | MS08-067 worked |
| Optimum | Windows | Got user shell, not SYSTEM |
| Bashed | Linux | Failed — found web shell but sent wrong POST param |
| Jerry | Windows | Failed — tried `tomcat:tomcat`, real password was in the 401 page |
| Nibbles | Linux | Failed — found the path but too late |

Network exploits went 4/4. Web app boxes went 0/3. The problem in all three failures was the same: the LLM couldn't see HTTP responses during execution, so it couldn't adapt when something was slightly off.

That's what v2 is trying to fix — building a coordinator that reads output and decides what to do next, rather than planning everything before running a single command.
