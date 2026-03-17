# PLANTE Project Memory

## Project Overview
PLANTE is an **automated penetration testing and exploitation framework** that uses AI/LLM to:
- Conduct autonomous reconnaissance on target systems
- Generate realistic multi-stage attack chains
- Execute exploitation sequences via Kali Linux
- Track all activities in a PostgreSQL database

This is a **research-focused cybersecurity project** for testing AI agents' capability to perform autonomous penetration testing against intentionally vulnerable systems (Metasploitable 2, DVL).

## Architecture

### 3-Phase Pipeline
1. **Reconnaissance**: Nmap scans, service enumeration via MCP tools on Kali
2. **Attack Chain Planning**: LLM generates multi-stage exploits (initial_access → privilege_escalation → persistence)
3. **Attack Execution**: SSH to Kali VM, execute chains, validate success, log results

### Key Components
- `agents/orchestrator.py` - Main execution engine (async SSH, attack chain parsing)
- `agents/tools/SSHKaliTool.py` - Async SSH client with tmux session management
- `agents/tools/KaliMCP.py` - MCP bridge to Kali tools
- `mcp/mcp_server.py` - FastMCP server running on Kali
- `agents/llms/OpenRouter.py` - OpenRouter API client (currently using grok-4)
- `agents/llms/AnythingLLM.py` - Local AnythingLLM wrapper
- `agents/logger.py` - PostgreSQL database logging

### Prompts
- `agents/prompts/recon_prompt.txt` - Reconnaissance instructions
- `agents/prompts/attack_chain_prompt.txt` - Attack chain generation
- `agents/prompts/execution_prompt.txt` - Execution instructions

## Tech Stack
- **Python** with LangChain, asyncssh, psycopg2
- **MCP (Model Context Protocol)** for tool bridging
- **PostgreSQL** (Supabase) for telemetry
- **Kali Linux VM** as attack platform
- **Metasploitable 2** as target
- **VirtualBox** for virtualization

## Environment Setup
Required `.env` variables:
- `KALI_IP`, `METASPLOITABLE_IP` - VM IP addresses
- `OPENROUTER_API_KEY` - For LLM access
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - Supabase PostgreSQL
- `ANYTHINGLLM_*` - For local LLM option

## Key Design Patterns
- **Persistent Sessions**: Metasploit via tmux for state preservation
- **Output Validation**: Checks for "session X opened", "uid=0(root)" for success
- **Stage-Based Execution**: Halts on first failure
- **Database-Centric**: All commands and results logged

## Project Structure
```
PLANTE/
├── agents/
│   ├── orchestrator.py      # Main engine
│   ├── logger.py            # DB logging
│   ├── config/              # Settings
│   ├── tools/               # SSH, MCP tools
│   ├── llms/                # LLM wrappers
│   ├── prompts/             # LLM prompt templates
│   └── helpers/             # Utilities
├── mcp/                     # MCP server
├── results/                 # Output JSON files
├── DB.md                    # Database schema
└── VM_SETUP_GUIDE.md        # Setup instructions
```

## Notes
- Target currently set to Metasploitable 2
- Using "x-ai/grok-4" model via OpenRouter
- SSH to Kali uses default credentials (kali:kali)

---

## Capstone Project: Failure-Adaptive Pivoting

### Problem Statement
Current PLANET Hacker success rate: ~40% (2/5 chains)
When remediation fails, system gives up instead of trying alternative exploits.

### Solution: Failure Classifier
Add failure classifier between Phase 4 (Remediation) and Phase 5 (Re-execution):
- **CORRECTABLE** failures → send to remediation (existing behavior)
- **FUNDAMENTAL** failures → pivot to different vulnerability/exploit

### Classifier Design
- Location: `CLASSIFIER_COMPLETE_DESIGN.md`
- Uses LLM (not if-statements) to classify error semantics
- Binary classification: CORRECTABLE vs FUNDAMENTAL
- Input: `execution_fix_output` JSON (shows if remediation already failed)
- Target accuracy: >75%
- Goal: Increase success rate to 55-65%

### Development Status
**Done (MacBook Air M4):**
- Python 3.11 virtual environment
- Dependencies installed
- OpenRouter API configured (Grok-4)
- Git initialized
- Classifier design documented

**Done (Windows PC):**
- VirtualBox 7.1.4 installed
- Kali Linux VM: `kali-linux-2025.4-virtualbox-amd64` at `192.168.56.100`
- Metasploitable 2 VM: `Metasploitable2` at `192.168.56.101`
- Host-Only Network configured with DHCP
- `.env` file configured with VM IPs and OpenRouter key

**Completed:**
- Baseline test runs documented in `docs/test_run_2026-01-26.md`
- Failure classifier implemented (`agents/classifier.py`)
- Classifier integrated into orchestrator pipeline
- Pushed to branch `feature/failure-classifier`
- Researched MAPTA paper + checked their GitHub repo
  - Their code is simpler than paper claims (single LLM loop with tools, not true multi-agent)
  - 76.9% success on XBOW benchmark

**Current Limitation (Why Classifier Alone Isn't Enough):**
The classifier is a **filter, not an improver**:
- CORRECTABLE → remediation → retry (existing behavior)
- FUNDAMENTAL → skip this chain, try next in batch
- When all chains in batch exhausted → **run ends**
- System never pivots to a DIFFERENT vulnerability/service

"Give up" = all chains from initial LLM batch are exhausted, no pivot to alternatives.

**Next Step: Pivot Feature**
When FUNDAMENTAL, instead of just skipping:
1. Go back to recon data
2. Pick a different vulnerable service
3. Generate new attack chain for that service
4. Try again

Implementation approach:
- Add `investigate_failure()` - run nc/nmap to gather evidence before classifying
- Add `pivot_to_alternative()` - query recon for other services, pick one
- Modify main loop to loop back instead of ending

### Cost
~$0.30-0.50 per full pentest run (OpenRouter/Grok-4)

