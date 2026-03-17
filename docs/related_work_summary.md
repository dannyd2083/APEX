# Related Work Summary for Professor Meeting
**Prepared by:** Danny
**Date:** 2026-01-26
**Purpose:** Understand what metrics other researchers use to evaluate automated penetration testing systems

---

## Quick Overview

I looked at the 4 papers the previous cohort cited. Here's what each one does and how they measured success:

| Paper | What It Does | Main Metric | Result |
|-------|--------------|-------------|--------|
| VulnBot | Multi-agent pentest system | Task completion rate | 30.3% overall |
| MAPTA | Web app pentesting | Success rate per vuln type | 76.9% overall |
| PentestGPT | Interactive pentest assistant | Improvement vs baseline | +228% vs GPT-3.5 |
| AutoRedTeamer | Red teaming with memory | Attack success + cost | +20% success, -46% cost |

---

## Paper 1: VulnBot (Kong et al., 2025)

### What It Does (Simple Version)
VulnBot is like having a team of AI specialists working together. Instead of one AI doing everything, it splits the work:

```
┌─────────┐    ┌─────────┐    ┌──────────────┐
│ Recon   │ →  │ Scanning│ →  │ Exploitation │
│ Agent   │    │ Agent   │    │ Agent        │
└─────────┘    └─────────┘    └──────────────┘
     ↑              ↑               ↑
     └──────────────┴───────────────┘
              Shared Memory (so they don't forget what happened)
```

**The Problem It Solves:** LLMs have short memory. If the recon agent finds something important, by the time the exploitation agent runs, the LLM might have "forgotten" it. VulnBot uses a shared memory system to fix this.

### How They Measured Success

| Metric | What It Means | Their Result |
|--------|---------------|--------------|
| **Subtask Completion Rate** | % of individual steps completed successfully | 69.05% |
| **Overall Completion Rate** | % of full attack chains that worked end-to-end | 30.3% |

### Why This Matters for My Project
- Their 30.3% overall completion is similar to the baseline (~40%)
- They measure SUBTASKS separately from OVERALL - I could do this too
- Shows that even good systems fail 70% of the time on full chains

---

## Paper 2: MAPTA (David & Gervais, 2025)

### What It Does (Simple Version)
MAPTA focuses specifically on web application hacking (not network services like we do). It has two parts:

```
┌─────────────┐         ┌─────────────┐
│ Coordinator │ ──────→ │  Sandbox    │
│ (plans the  │         │ (actually   │
│  attack)    │ ←────── │  tries it)  │
└─────────────┘         └─────────────┘
```

**Cool Feature:** It doesn't just find vulnerabilities - it actually PROVES they work by running the exploit in a sandbox. This separates "theoretically vulnerable" from "actually exploitable."

### How They Measured Success

They used something called the **XBOW Benchmark** (104 challenges across different vulnerability types):

| Vulnerability Type | Success Rate | What It Is |
|-------------------|--------------|------------|
| SSRF | 100% | Tricking server to make requests |
| Misconfiguration | 100% | Wrong settings (default passwords, etc.) |
| Server-Side Template Injection | 85% | Injecting code into templates |
| SQL Injection | 83% | Database attacks |
| Broken Authorization | 83% | Accessing stuff you shouldn't |
| **Overall** | **76.9%** | Average across all types |

### Interesting Finding
They discovered: **If an attack takes too long, it's probably not going to work.**

> "Negative correlations between resource utilization and success, providing actionable early-stopping heuristics"

Translation: If you've been trying for a while and it's not working, stop and try something else. **This is basically what my classifier does!**

### Why This Matters for My Project
- They break down success BY VULNERABILITY TYPE - I could do this
- Their "early stopping" idea is similar to my FUNDAMENTAL classification
- 76.9% is high, but they're testing web apps (different from network services)

---

## Paper 3: PentestGPT (Deng et al., 2024)

### What It Does (Simple Version)
PentestGPT is like a senior pentester guiding a junior one. It doesn't fully automate the attack - it gives you advice on what to do next.

```
Human: "I found port 21 open with vsftpd 2.3.4"
   │
   ▼
┌─────────────────────────────────────────────┐
│ PentestGPT                                  │
│                                             │
│ "That version has a known backdoor.         │
│  Try: use exploit/unix/ftp/vsftpd_234...    │
│  Here's what to do next..."                 │
└─────────────────────────────────────────────┘
```

**Key Concept: Penetration Testing Tree (PTT)**
They track everything as a tree of tasks:

```
Root: Hack the target
├── Recon
│   ├── Port scan ✓
│   └── Service detection ✓
├── Exploit vsftpd
│   ├── Load module ✓
│   ├── Set options ✓
│   └── Run exploit ← Currently here
└── Exploit Samba
    └── (not started)
```

This prevents the LLM from forgetting what's been done and what's left to do.

### How They Measured Success

| Metric | What It Means | Their Result |
|--------|---------------|--------------|
| **Task Completion Increase** | How much better than baseline (GPT-3.5 alone) | **+228.6%** |

This means PentestGPT completed 3.3x more tasks than just using GPT-3.5 directly.

### Why This Matters for My Project
- They compare against a BASELINE (raw GPT-3.5) - I should compare with/without classifier
- The "tree" concept helps track progress - similar to tracking which chains succeeded/failed
- +228% is a big improvement, shows that smart orchestration matters

---

## Paper 4: AutoRedTeamer (Zhou et al., 2025)

### What It Does (Simple Version)
AutoRedTeamer is about attacking AI systems (not servers), but the concept is useful. It has two agents:

```
┌──────────────────┐      ┌───────────────────┐
│ Red Team Agent   │      │ Strategy Proposer │
│ (runs attacks)   │ ←──→ │ (finds new attacks│
│                  │      │  from research)   │
└──────────────────┘      └───────────────────┘
         │
         ▼
    ┌─────────┐
    │ Memory  │  ← Remembers what worked and what didn't
    └─────────┘
```

**Key Feature: Memory of What Works**
It tracks which attacks succeed and which fail, then uses this to pick better attacks next time. Over time, it gets smarter about what to try.

### How They Measured Success

| Metric | What It Means | Their Result |
|--------|---------------|--------------|
| **Attack Success Rate** | % of attacks that worked | +20% vs baseline |
| **Computational Cost** | How much compute/money spent | -46% reduction |

### Why This Matters for My Project
**This is the most relevant paper for my classifier!**

They measure TWO things:
1. Success rate (did it work better?)
2. Cost/efficiency (did it waste less resources?)

My classifier is about #2 - not wasting time on FUNDAMENTAL failures. I should measure:
- How many remediation attempts were SKIPPED
- How much time/money was SAVED
- Whether skipping hurt or helped overall success

---

## Summary: Metrics I Should Use

Based on these papers, here are the metrics that make sense for evaluating my classifier:

### Primary Metrics (Must Have)

| Metric | Description | How to Measure |
|--------|-------------|----------------|
| **Classifier Accuracy** | Did it correctly identify CORRECTABLE vs FUNDAMENTAL? | Manual review of each classification |
| **Remediation Attempts Saved** | How many chains were skipped? | Count FUNDAMENTAL chains |
| **Overall Success Rate** | Did adding the classifier help or hurt? | Compare with/without classifier |

### Secondary Metrics (Nice to Have)

| Metric | Description | How to Measure |
|--------|-------------|----------------|
| **False Positive Rate** | Said FUNDAMENTAL but was actually fixable | Manual review |
| **False Negative Rate** | Said CORRECTABLE but was actually unfixable | Manual review |
| **Cost Savings** | Money saved by skipping FUNDAMENTAL | API costs avoided |
| **Time Savings** | Time saved by skipping FUNDAMENTAL | Execution time comparison |
| **Per-Vulnerability Breakdown** | Success rate by vuln type (vsftpd, Samba, etc.) | Track per chain |

### Comparison Format (Like the Papers)

| Metric | Without Classifier | With Classifier | Change |
|--------|-------------------|-----------------|--------|
| Overall success rate | X% | Y% | +/-Z% |
| Remediation attempts | N | M | -K saved |
| Cost per run | $A | $B | -$C saved |
| Time per run | Xmin | Ymin | -Zmin saved |

---

## Questions for Professor

1. **Is classifier accuracy enough, or do I need to show overall success improvement?**
   - The papers show both, but my classifier's main job is efficiency, not success

2. **Should I create a fixed test set (same 5 chains every time)?**
   - This would allow apples-to-apples comparison
   - But it's "artificial" - real system would generate different chains

3. **How many test runs do I need for statistical significance?**
   - Papers don't always say how many runs they did
   - Should I run 5x? 10x?

4. **Is comparing to the previous cohort's baseline valid?**
   - We used different attack chains
   - Same target though

---

## My Current Results vs Papers

| System | Overall Success | Notes |
|--------|----------------|-------|
| VulnBot | 30.3% | Multi-agent |
| MAPTA | 76.9% | Web apps only |
| PentestGPT | +228% vs baseline | Interactive, not autonomous |
| Previous Cohort | 40% → 60% | With remediation |
| **My Run** | 50% (2/4) | With classifier |

My results are in the same ballpark, but hard to compare directly because:
- Different targets
- Different vulnerability types
- Different chain counts

---

## TL;DR for Professor

1. **What I built:** A classifier that decides if a failed attack is worth retrying or should be skipped

2. **Why it matters:** Saves time and money by not trying to fix unfixable things

3. **How others measure this:**
   - Success rate (did more attacks work?)
   - Efficiency (did we waste less resources?)
   - Comparison to baseline (how much better?)

4. **My challenge:** The LLM generates different attack chains each run, making comparison tricky

5. **Proposed solution:** Either fix the chains for fair comparison, or focus on classifier-specific metrics (accuracy, false positive rate, cost savings)
