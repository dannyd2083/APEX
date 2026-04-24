# APEX — Autonomous Penetration and EXploitation

An autonomous penetration testing agent that runs end-to-end against real HackTheBox machines. APEX combines a coordinator-driven multi-agent loop, a three-class failure taxonomy with code-enforced loop detection, and two complementary RAG systems to avoid repeating failed approaches.

**Results**: 30/42 HackTheBox machines (71.4%) — 22/27 Easy (81.5%), 8/15 Medium (53.3%).

This project was inherited from the 2025 cohort (original v1 codebase) and extended with a full v2 rewrite for the 2026 capstone.

---

## Original Architecture (v1)

The original system plans everything upfront and executes blindly — the LLM never sees HTTP responses during execution.

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
└─────────────────┘
```

Pipeline: `Recon → LLM plans all commands upfront → Execute → Done`

---

## v2 Architecture (APEX)

Three agents work in a closed loop. The coordinator reads command output before deciding what to do next, maintains a persistent task tree across turns, and applies failure classification to avoid retrying dead-end approaches.

```
┌──────────────────────────────────────────────┐
│                Windows Host                  │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │             Coordinator                 │ │
│  │  - Maintains task tree (PTT)            │ │
│  │  - Classifies failures (3-class)        │ │
│  │  - Queries PayloadsRAG + ErrorRAG       │ │
│  └────────────┬──────────────┬─────────────┘ │
│               │              │               │
│        ┌──────▼──────┐ ┌─────▼──────┐        │
│        │ Recon Agent │ │Execute Agent│        │
│        │ nmap/gobust │ │ bash script │        │
│        │ ZAP/sqlmap  │ │ HTTP tools  │        │
│        └──────┬──────┘ └─────┬──────┘        │
│               └──────┬───────┘               │
│                      ▼                       │
│               ┌─────────────┐                │
│               │  Kali VM    │                │
│               │ (via MCP)   │                │
│               └─────────────┘                │
└──────────────────────────────────────────────┘
```

### Key Design Decisions

**Failure taxonomy (3 classes)**
- `SCRIPT_ERROR` — the generated script has a syntax/runtime error; trigger repair mode (max 2 retries)
- `FIXABLE` — the output tells you exactly what to change; retry once with that fix
- `FUNDAMENTAL` — the approach is incompatible with the target (wrong service version, payload stripped, endpoint absent); abandon the task

**Code-enforced loop detection (3 counters)**
- `_exec_fail_streak` — 2 consecutive execute failures → inject LOOP DETECTED warning
- `_fundamental_streak` — 2 consecutive FUNDAMENTAL classifications → auto-fail the task (in code, not prompt)
- `_child_fail_count` — 8 failed child tasks under same parent → auto-fail the parent

**Two RAG systems**
- `PayloadsRAG` — BM25 over PayloadsAllTheThings; queried every turn to inject relevant attack techniques
- `Error Path RAG` — BM25 over past FUNDAMENTAL failures stored in Supabase; cross-run failure memory

**One-turn lag judgment** — the execute agent never declares success; the coordinator evaluates the raw output one turn later with full task context, producing more accurate success/failure judgments.

---

## Setup

### 1. Kali VM

1. Download Kali Linux from [kali.org](https://www.kali.org/get-kali/#kali-virtual-machines) and import into VirtualBox
   - Adapter 1: Host-Only (for host ↔ VM comms)
   - Adapter 2: NAT (for internet / HTB VPN)

2. Clone MCP-Kali-Server on the Kali VM:
   ```bash
   git clone https://github.com/Wh0am123/MCP-Kali-Server.git
   cd MCP-Kali-Server && python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Start services on Kali before each run:
   ```bash
   # API server (must use --ip 0.0.0.0)
   nohup python3 kali_api_server.py --ip 0.0.0.0 > /tmp/mcp.log 2>&1 &

   # HTB VPN
   sudo openvpn --config ~/machines_us-dedivip-1.ovpn --daemon

   # OWASP ZAP (for web recon)
   nohup zaproxy -daemon -port 8080 -host 0.0.0.0 -config api.disablekey=true > /tmp/zap.log 2>&1 &
   ```

### 2. Windows Host

```bash
git clone https://github.com/dannyd2083/APEX.git
cd APEX
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Mac/Linux
pip install -r requirements.txt
```

### 3. Environment

Copy `.env.example` to `.env` and fill in:

```bash
KALI_IP=192.168.56.101         # your Kali host-only IP
OPENROUTER_API_KEY=sk-or-v1-...
TESTER_NAME=YourName

# Optional — only needed for Error Path RAG persistence
DB_HOST=db.your-project.supabase.co
DB_PASSWORD=...
```

### 4. VirtualBox Network

File → Host Network Manager → create a Host-Only network with DHCP. Assign each VM Adapter 1 = Host-Only. Find IPs with `ip addr` inside each VM.

---

## Running

```bash
.\venv\Scripts\activate   # Windows
python -m agents.coordinator --target-ip <IP> --target-os <OS> --target-name <Name>
```

Results are saved to `results/v2/<Name>_<timestamp>/run.md` and `run.json`.

**Cost**: ~$0.40–1.00 per easy box, ~$2–3 per medium box (Claude Opus 4.6 coordinator + Sonnet 4.6 workers via OpenRouter).

---

## Repo Structure

```
agents/
├── coordinator.py          # Main loop: task tree, failure classification, RAG
├── recon_agent.py          # Recon: nmap, gobuster, ZAP, sqlmap, curl
├── execute_agent.py        # Exploitation: bash scripts, HTTP session tools
├── state.py                # PentestState: task tree, findings, key_facts
├── config/                 # settings.py, constants.py (models, limits)
├── helpers/
│   ├── payloads_rag.py     # BM25 RAG over PayloadsAllTheThings
│   ├── error_rag.py        # BM25 RAG over past FUNDAMENTAL failures
│   ├── run_logger.py       # Writes results/v2/ logs
│   ├── token_tracker.py    # Per-call cost tracking
│   └── output_parsers.py   # Deterministic parsers for nmap/gobuster/ZAP output
├── llms/
│   └── OpenRouter.py       # OpenRouter API client
├── prompts/                # LLM prompt templates
└── tools/
    └── KaliMCP.py          # MCP client → kali_bridge.py → Kali REST API

mcp/
└── kali_bridge.py          # FastMCP bridge (Windows side)

tests/
└── test_error_rag.py       # Unit tests for Error Path RAG (no DB needed)

config_files/               # MCP config templates for Claude Desktop / 5ire
results/                    # Local run output (gitignored)
```

---

## Troubleshooting

**Kali API not reachable from host**
```bash
# Must start with --ip 0.0.0.0, not default 127.0.0.1
python3 kali_api_server.py --ip 0.0.0.0
```

**Port 5000 occupied on Kali**
```bash
sudo kill -9 $(sudo lsof -t -i :5000)
```

**OpenRouter 402 error** — add credits at openrouter.ai/settings/credits

---

## Capstone 2026

We tested v1 on 7 HTB machines and found the core limitation: the LLM plans commands upfront with no feedback loop, so it cannot adapt when a service responds unexpectedly. Web app boxes all failed; network CVE boxes worked.

v2 (APEX) addresses this with a coordinator that reads output before each decision. On 42 HTB machines:

| Difficulty | Success |
|------------|---------|
| Easy (27)  | 22/27 (81.5%) |
| Medium (15)| 8/15 (53.3%) |
| **Total**  | **30/42 (71.4%)** |

The main failure categories were JavaScript-managed form fields (Joomla 4 CodeMirror — raw HTTP POST silently ignored without a browser), PHP execution restrictions (filter chain RCE, phar.readonly), and WebSocket blind SQLi (too slow for the turn budget).

See `docs/capstone_report.pdf` for the full paper.
