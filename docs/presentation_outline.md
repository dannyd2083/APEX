# PLANTE: AI-Driven Automated Penetration Testing
## Presentation Outline — Danny Deng | Capstone Project | Feb 2026

---

## Slide 1: Title

**PLANTE: AI-Driven Automated Penetration Testing**

Danny Deng | Capstone Project | Feb 2026

---

## Slide 2: What is PLANTE?

- AI framework that **automatically hacks vulnerable machines**
- Uses LLM (Grok-4 via OpenRouter) to plan and execute attacks
- Targets: Metasploitable 2, HackTheBox machines
- Built by previous cohort (Alyssa), we inherited and improved it
- Runs on Kali Linux VM, controlled from Windows host

---

## Slide 3: Original Architecture

**One big Python script (`orchestrator.py`, 754 lines)**

5 phases, runs once, top to bottom:

```
Recon (nmap) → LLM plans ALL commands → Execute blindly → If fail, LLM rewrites → Retry once → Done
```

- LLM generates a complete JSON with every command before execution starts
- PLANTE runs commands without understanding the output
- If retry fails → run ends, no more attempts

**Diagram:** Simple left-to-right pipeline with 5 boxes:
```
[Recon] → [Attack Chain Gen] → [Execute] → [Remediate] → [Re-execute]
  nmap      LLM plans ALL        Run          LLM fixes     Try again
  scan      commands upfront     blindly      syntax         once
```

---

## Slide 4: How It Executes

- PLANTE SSHs into Kali Linux VM
- Runs commands one by one in order (via tmux terminal sessions)
- Checks output for keywords:
  - `"session opened"` = success
  - `"exploit failed"` = failure
- It's a **blind dispatcher** — doesn't understand what the output means
- Two channels: MCP for scanning, SSH for attacking (completely separate)

---

## Slide 5: Problems with Original

1. **Single-pass** — all chains fail = game over, no learning
2. **No failure analysis** — doesn't investigate WHY it failed
3. **Hardcoded** — Linux-only, one payload, one target type
4. **Can't do web apps** — plans everything upfront, can't read HTTP responses

---

## Slide 6: What We Changed (Overview)

**10 commits, 754 → 1288 lines**

- **Failure Classifier** — sorts failures into CORRECTABLE vs FUNDAMENTAL
- **Investigation Phase** — checks: port open? version match? module exist?
- **3-Round Feedback Loop** — failed context feeds into next attempt
- **Multi-OS Support** — Linux, Windows, FreeBSD
- **CLI for multi-target** — `--target-ip`, `--target-os`, `--target-name`
- **Auto-detect VPN IP** — for reverse shells (tun0 interface)
- **Cost tracking** — tracks API spend per phase
- **Generalization audit** — removed 8 hardcoded values

**Diagram:** Updated pipeline showing the new loop:
```
[Recon] → [Attack Chain Gen] → [Execute] → [Classify Failure]
  nmap      LLM plans              Run         ↓
  scan      commands               blindly    CORRECTABLE → [Remediate] → [Re-execute]
                                              FUNDAMENTAL → [Investigate] → back to Attack Chain Gen
                                                             (up to 3 rounds)
```

---

## Slide 7: Failure Classifier

**Before (original):** Try to fix EVERYTHING, even impossible exploits

**After (ours):**

1. Run diagnostics first (is port open? what version?)
2. LLM classifies: **CORRECTABLE** (fix it) vs **FUNDAMENTAL** (skip it)

| Example | Classification | Action |
|---------|---------------|--------|
| Wrong OS exploit (DCOM on Windows 7) | FUNDAMENTAL | Skip immediately |
| Wrong payload type | CORRECTABLE | Try different payload |
| Patched vulnerability (vsftpd on Lame) | FUNDAMENTAL | Skip, try different service |
| Missing MSF option | CORRECTABLE | Add the option and retry |

---

## Slide 8: Feedback Loop

**Before:** Fail → Done.

**After:** Fail → Learn → Try again (up to 3 rounds)

- Round 1 failures + discoveries go into Round 2's LLM prompt
- *"Don't repeat failed approaches. Use these discoveries instead."*
- Round 2 failures + Round 1 failures go into Round 3's prompt

**Example (Bashed box):**

| Round | What happened | What fed forward |
|-------|--------------|-----------------|
| 1 | Shellshock failed (incompatible payload) | "Shellshock doesn't work, try something else" |
| 2 | Same modules with different payloads | "These modules don't work AT ALL" |
| 3 | LLM pivoted to `phpbash.php` webshell | **Found the correct exploit path** |

---

## Slide 9: Test Results (7 HackTheBox Boxes)

| Box | OS | Result | Key Exploit |
|-----|-----|--------|-------------|
| Lame | Linux | **1/2 (50%)** | Samba CVE-2007-2447 → root |
| Blue | Windows | **1/2 (50%)** | EternalBlue MS17-010 → SYSTEM |
| Legacy | Windows | **1/2 (50%)** | MS08-067 → SYSTEM |
| Optimum | Windows | **PARTIAL** | HFS RCE → user shell (kostas), no SYSTEM |
| **Bashed** | **Linux** | **0/5 FAILED** | Found webshell in R3, wrong POST param |
| **Jerry** | **Windows** | **0/6 FAILED** | Wrong creds, never scraped error page |
| **Nibbles** | **Linux** | **0/5 FAILED** | Found `/nibbleblog/` in R3, ran out of rounds |

**Network exploits: 4/4 success. Web apps: 0/3 failure.**

---

## Slide 10: Why Web Boxes Failed

**Root cause: LLM can't see HTTP responses mid-execution**

**Bashed:**
- LLM found the webshell, sent `curl -d "c=whoami" .../phpbash.php`
- The HTML response showed the correct parameter is `cmd=`, not `c=`
- But PLANTE never showed the response back to the LLM

**Jerry:**
- LLM tried `tomcat:tomcat` → 401 error
- The 401 page contained the real password (`s3cret`)
- But LLM never saw the 401 page

**Nibbles:**
- LLM found `/nibbleblog/` in Round 3 HTML comment
- But Round 3 was the last round — no Round 4 to act on the discovery

**Conclusion: Planning everything upfront can't solve web pentesting.**

---

## Slide 11: What's Next — Multi-Agent Architecture

**Current:** One big script plans everything, executes blindly

**Proposed:** Multiple agents, each with a job, working together

3 agents (all use same LLM, same Kali VM, same Python process — NOT a distributed system):

1. **Coordinator** — the brain, makes all decisions
2. **Recon Agent** — scans targets (nmap, gobuster, curl)
3. **Execution Agent** — runs commands via SSH, reports output back

**Diagram:** Coordinator at top, two workers below, arrows going both ways:
```
              ┌─────────────┐
              │ COORDINATOR │
              │  (the brain) │
              └──────┬──────┘
                ↕         ↕
     ┌──────────┐   ┌───────────┐
     │  RECON   │   │ EXECUTION │
     │  AGENT   │   │   AGENT   │
     │ nmap,    │   │ ssh,      │
     │ gobuster,│   │ msf,      │
     │ curl     │   │ curl      │
     └──────────┘   └───────────┘
```

---

## Slide 12: How It Works (Pseudocode)

```
COORDINATOR: "Recon Agent, scan the target"
RECON AGENT: runs nmap → "Found Apache on port 80"

COORDINATOR: "Execution Agent, run: curl http://target/"
EXECUTION AGENT: runs curl → returns HTML page

COORDINATOR: reads HTML, sees login form
COORDINATOR: "Execution Agent, run: curl -d 'user=admin&pass=s3cret' ..."
EXECUTION AGENT: runs curl → "Welcome admin!"

COORDINATOR: "We're in. Now try privilege escalation..."
... loop until done or give up
```

**Key difference:** see output → decide next step → repeat

**Not:** plan everything → execute blindly → hope it works

---

## Slide 13: Why This Fixes Web Boxes

| Problem | Before (Batch) | After (Interactive) |
|---------|----------------|---------------------|
| Wrong POST param (Bashed) | Can't see response to correct it | Coordinator reads HTML, finds correct param |
| Wrong password (Jerry) | Can't see error page | Coordinator reads 401 page, finds hint |
| Hidden directory (Nibbles) | Found too late (Round 3) | Found immediately, acted on right away |

The coordinator **observes and adapts** in real-time, just like a human pentester.

---

## Slide 14: Expected Results

|  | Current (Batch Pipeline) | Proposed (Multi-Agent) |
|---|---|---|
| Network exploits | 4/4 (100%) | Keep working |
| Web app boxes | 0/3 (0%) | Should improve |
| Overall | 4/7 (57%) | Target: 70-85% |
| Cost per run | $0.20-1.40 | Similar |

---

## Slide 15: Next Steps

1. Build agent classes (Coordinator, ReconAgent, ExecutionAgent)
2. Reuse existing SSH/MCP tools (no infrastructure changes)
3. Write coordinator prompt (the key intelligence)
4. Test on failed web boxes (Bashed, Jerry, Nibbles)
5. Compare: batch pipeline vs multi-agent results
6. Web-focused: drop Metasploit, focus on curl/sqlmap/web tools

---

## Appendix: Cost Summary

| Box | Runs | Total Cost | Result |
|-----|------|-----------|--------|
| Lame | 4 | ~$0.36 | 50% (Run 4) |
| Blue | 3 | ~$0.57 | 50% (Run 3) |
| Legacy | 3 | ~$1.24 | 50% (Run 3) |
| Optimum | 1 | $0.14 | Partial |
| Bashed | 2 | ~$0.74 | 0% |
| Jerry | 1 | $0.64 | 0% |
| Nibbles | 1 | $0.30 | 0% |
| **Total** | **15** | **~$3.99** | **4/7 (57%)** |

## Appendix: Bugs Fixed During Testing

| Bug # | Description | Impact | Fix |
|-------|-------------|--------|-----|
| 1 | Investigation searched MSF by Nmap service name | Classifier falsely said modules don't exist | Search by exploit module name |
| 2 | Crash on malformed LLM response | Lost all round data | `.get()` instead of direct key access |
| 3 | Result saving inside `try` block | Crash = no files saved | Moved to `finally` block |
| 4 | Wait times not logged | Couldn't diagnose timing issues | Added wait logging |
| 5 | Recon-only chains counted as success | Feedback loop didn't run | Stage classification fix |
| 6 | No session retry for slow exploits | EternalBlue failed despite working | 20s retry mechanism |
| 7 | Port-open check after exploit crashes service | False "port closed" → FUNDAMENTAL | Check exploit output for connection evidence |
| 8 | Wrong TARGET for buffer overflows | MS08-067 crashed service with wrong offset | Prompt: use TARGET 0 (Automatic) |
