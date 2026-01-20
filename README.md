# AI Battle Bots with MCP

An AI-powered automated penetration testing framework that uses LLM agents to conduct autonomous reconnaissance and exploitation against intentionally vulnerable systems.

## Architecture Overview

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

## Document Source
- [LangChain](https://docs.langchain.com/oss/python/langchain/overview)
- [AnythingLLM](https://docs.anythingllm.com/introduction)

## DVL Source
- [DVL](https://www.vulnhub.com/series/damn-vulnerable-linux-dvl,1/)
- [DVL Setup](https://github.com/alyssarusk/ai-battle-bots/blob/main/DVL.md)

## Setup

### 1. mcp-kali-server
MCP bridging Kali VM and Agents [Github](https://github.com/Wh0am123/MCP-Kali-Server).

#### 1.1 Setting up on Kali VM

1. Download and import Kali VM from [offical website](https://www.kali.org/get-kali/#kali-virtual-machines)
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

2. Fix logging errors in `mcp_server.py` file by changing:

    ```python
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout) # This line needs changing
        ]
    )
    ```

    To:
    ```python
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr) # Change to this
        ]
    )
    ```

3. Start server
    ```
    python kali_server.py
    ```

### 2. redstack-vault
#### 2.1 Start Server
Navigate to redstack-vault/.mcp-server
Run
```
./start.sh
```

### 3. Project Installation
```
pip install -r requirements.txt
```

**Additional packages needed:**
```
pip install langchain-mcp-adapters asyncssh paramiko scp
```

**Packages**
- langchain
- langchain_openai - OpenAI-compatible models
- mcp - connection to MCP servers
- python-dotenv - manage env variables
- requests - needed to connect to APIs (AnythingLLM)
- psycopg2 - connecting to db

### 4. Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
# VM IP Addresses (find yours with `ip addr` in each VM)
KALI_IP=<your-kali-ip>
METASPLOITABLE_IP=<your-metasploitable-ip>

# OpenRouter LLM
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Tester Name (for result files)
TESTER_NAME=YourName

# AnythingLLM (optional)
ANYTHINGLLM_API_KEY=your-key
ANYTHINGLLM_API_URL=http://localhost:3001/api/v1
ANYTHINGLLM_WORKSPACE_SLUG=plante

# Supabase Database
DB_HOST=your-project.supabase.co
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your-password
DB_NAME=postgres
DB_SSLMODE=require
```

### 5. VirtualBox Network Setup

Each setup may have different IP addresses depending on your VirtualBox configuration.

1. Open VirtualBox > File > **Host Network Manager**
2. Create or select a Host-Only Network
3. Enable DHCP Server (or configure static IPs)
4. For each VM, go to Settings > Network:
   - **Adapter 1**: Host-Only Adapter (select your network)
   - **Adapter 2** (Kali only): NAT (for internet access)
5. Start VMs and find their IPs:
   ```bash
   # In each VM terminal
   ip addr
   ```
6. Update your `.env` file with the discovered IPs

**Note**: Your IPs will likely differ from others. Common ranges are `192.168.56.x` or `192.168.x.x` depending on your Host-Only network configuration.

## Repo Folders
### agents
Python files for agents created using Langchain.

Currently containing agent:
- Orchestrator

*get_workspaces.py can be used to find AnythingLLM workplace slugs*

### config_files
json files needed to connect the Kali MCP to the LLM.

Currently containing config file for:
- AnythingLLM

### docs/weekly_updates
Weekly progress reports.

### results/
Output JSON files from test runs.

## Running the Orchestrator

```bash
# Activate venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate # Mac/Linux

# Run orchestrator
python agents/orchestrator.py
```

## Troubleshooting

### Kali Server Not Accessible from Host

**Symptom**: `curl http://<kali-ip>:5000/health` fails from host machine

**Solution**: Start server with `--ip 0.0.0.0`:
```bash
python3 kali_server.py --ip 0.0.0.0
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

**Solution**: Fixed in `agents/helpers/save_json.py` - colons replaced with dashes in timestamps

## Cost Estimates

- **OpenRouter (Grok-4)**: ~$0.30-0.50 per full pentest run
- **Supabase**: Free tier sufficient for testing
- **AnythingLLM**: Free (uses your own API keys)

## Capstone Project (2026)

Potential research direction: Improving the system's ability to handle failed exploits by exploring alternative attack paths when initial attempts fail. Details TBD.

## Contributors

- Danny (Capstone 2026)
- Previous cohort: Alyssa, Nina (2025)
