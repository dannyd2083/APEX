# PLANTE Adaptive Pivoting Feature

**Project Type:** Capstone Extension of PLANTE
**Author:** Danny
**Date:** 2026-02-04

---

## Goal

Improve PLANTE's success rate by adding **adaptive pivoting** - when an exploit fundamentally can't work, try a different vulnerability instead of giving up.

**Target:** Improve success rate from ~40% to 55-65%

---

## Current Problem

```
LLM generates chains → Execute → Fail → Remediate → Fail again → GIVE UP
```

The system never tries a DIFFERENT vulnerable service. It just stops.

---

## Solution: Investigation + Pivot

```
Execute → Fail → INVESTIGATE → Classify → PIVOT to different service → Try again
```

Two new features:
1. **Investigation**: Verify facts before classifying (don't let LLM guess)
2. **Pivot**: Try different service when current one is fundamentally broken

---

## New Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. RECON (existing)                                         │
│    Nmap scan → find services                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────────────────────────┐
         │            PIVOT LOOP (NEW)            │
         │         max 3 pivot attempts           │
         └────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. GENERATE ATTACK CHAINS (existing)                        │
│    LLM picks vulnerabilities → generates chains             │
│    (exclude already-tried services)                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. EXECUTE (existing)                                       │
│    Run Metasploit → check for shell                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
                        Success? ──Yes──→ Done ✓
                              │
                             No
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. INVESTIGATE (NEW)                                        │
│    - nc -zv: Is port still open?                            │
│    - nmap -sV: What version is running?                     │
│    - msfconsole search: Does module exist?                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. CLASSIFY (existing, now with evidence)                   │
│    Input: error message + investigation evidence            │
│    Output: CORRECTABLE or FUNDAMENTAL                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
            ┌─────────────────┴─────────────────┐
            ↓                                   ↓
      CORRECTABLE                          FUNDAMENTAL
            ↓                                   ↓
┌───────────────────────┐              ┌───────────────────────┐
│ 6. REMEDIATE          │              │ 7. PIVOT (NEW)        │
│    (existing)         │              │    Mark service tried │
│    Fix and retry      │              │    Pick new service   │
└───────────────────────┘              │    Go to step 2       │
                                       └───────────────────────┘
```

---

## Implementation

### New Function 1: `investigate_failure()`

Location: `agents/orchestrator.py`

```python
async def investigate_failure(ssh, target_ip, port, service_name, error_msg):
    """
    Gather FACTS before classifying. Don't let LLM guess.

    Returns dict with:
    - port_open: bool
    - actual_version: str
    - module_exists: bool
    """
    evidence = {}

    # Check 1: Is port open?
    result = await ssh.execute(f"nc -zv {target_ip} {port} 2>&1")
    evidence['port_open'] = "open" in result.lower() or "succeeded" in result.lower()

    # Check 2: What version is actually running?
    result = await ssh.execute(f"nmap -sV -p {port} {target_ip}")
    evidence['actual_version'] = parse_version_from_nmap(result)

    # Check 3: Does Metasploit module exist?
    result = await ssh.execute(f"msfconsole -q -x 'search type:exploit name:{service_name}; exit'")
    evidence['module_exists'] = "exploit/" in result.lower()

    return evidence
```

### New Function 2: `pivot_to_alternative()`

Location: `agents/orchestrator.py`

```python
def pivot_to_alternative(recon_data, tried_services):
    """
    Pick a different vulnerable service from recon data.

    Args:
        recon_data: Original nmap scan results
        tried_services: Set of service names we already attempted

    Returns:
        Next service to try, or None if exhausted
    """
    # Known vulnerable services on Metasploitable 2
    # Ordered by reliability
    priority_services = [
        'vsftpd',      # Easy backdoor
        'samba',       # usermap_script reliable
        'distcc',      # Command execution
        'unrealircd',  # Backdoor
        'postgres',    # Weak creds
        'tomcat',      # Manager upload
        'mysql',       # Weak creds
        'telnet',      # Weak creds
    ]

    for service in priority_services:
        if service not in tried_services:
            # Verify it's in recon data
            if service_in_recon(recon_data, service):
                return service

    return None  # Nothing left
```

### Modified Main Loop

Location: `agents/orchestrator.py`

```python
async def run_attack_with_pivot(target_ip):
    """Main attack loop with adaptive pivoting."""

    # Step 1: Recon
    recon_data = await run_recon(target_ip)

    tried_services = set()
    max_pivots = 3

    for pivot_num in range(max_pivots):
        # Step 2: Generate chains (exclude tried services)
        chains = await generate_attack_chains(
            recon_data,
            exclude_services=tried_services
        )

        if not chains:
            print("No more attack chains to try")
            break

        for chain in chains:
            current_service = extract_service_name(chain)

            # Step 3: Execute
            result = await execute_chain(chain)

            if result.success:
                return {"status": "SUCCESS", "chain": chain}

            # Step 4: Investigate
            evidence = await investigate_failure(
                ssh_client,
                target_ip,
                chain.port,
                current_service,
                result.error
            )

            # Step 5: Classify (with evidence)
            classification = await classify_with_evidence(
                result.error,
                evidence
            )

            if classification == "CORRECTABLE":
                # Step 6: Remediate (existing)
                fixed_chain = await remediate(chain, result.error)
                retry_result = await execute_chain(fixed_chain)

                if retry_result.success:
                    return {"status": "SUCCESS", "chain": fixed_chain}

            # Mark this service as tried
            tried_services.add(current_service)

        # Step 7: Pivot
        next_service = pivot_to_alternative(recon_data, tried_services)

        if next_service is None:
            print("All services exhausted")
            break

        print(f"PIVOT: Trying {next_service} instead...")

    return {"status": "FAILED", "tried": list(tried_services)}
```

---

## Classifier Update

Modify `agents/classifier.py` to accept evidence:

```python
async def classify_with_evidence(error_msg, evidence):
    """
    Classify failure using both error message AND investigation evidence.
    """

    # Hard rules based on evidence (no LLM needed)
    if not evidence['port_open']:
        return "FUNDAMENTAL"  # Port closed, can't exploit

    if not evidence['module_exists']:
        return "FUNDAMENTAL"  # No Metasploit module available

    # For ambiguous cases, use LLM with evidence context
    prompt = f"""
    Error: {error_msg}

    Investigation results:
    - Port open: {evidence['port_open']}
    - Actual version: {evidence['actual_version']}
    - Metasploit module exists: {evidence['module_exists']}

    Is this CORRECTABLE (can fix with config change) or FUNDAMENTAL (need different vulnerability)?

    Answer with just: CORRECTABLE or FUNDAMENTAL
    """

    response = await llm.ask(prompt)
    return response.strip().upper()
```

---

## Implementation Steps

| Step | Task | Files | Effort |
|------|------|-------|--------|
| 1 | Add `investigate_failure()` | `orchestrator.py` | 1-2 hours |
| 2 | Update classifier to use evidence | `classifier.py` | 1 hour |
| 3 | Add `pivot_to_alternative()` | `orchestrator.py` | 1 hour |
| 4 | Modify main loop for pivoting | `orchestrator.py` | 2-3 hours |
| 5 | Test on Metasploitable 2 | - | 1-2 hours |
| 6 | Add Kioptrix VM to benchmark | - | 1 hour |
| 7 | Run before/after comparison | - | 2 hours |
| 8 | Document results | `docs/` | 1 hour |

**Total: ~10-12 hours of work**

---

## Benchmark Plan

### Targets

| VM | Services to Test | Source |
|----|-----------------|--------|
| Metasploitable 2 | vsftpd, samba, distcc, unrealircd | Already have |
| Kioptrix Level 1 | samba, apache, ssh | VulnHub (free) |

### Metrics

| Metric | Baseline (current) | Target (with pivot) |
|--------|-------------------|---------------------|
| Success rate | ~40% (2/5 runs) | 55-65% |
| Services exploited | 1-2 per run | 2-3 per run |
| Wasted retries | 3-5 | 0-1 |

### Test Protocol

```
1. Run PLANTE 5 times WITHOUT pivot feature
   - Record: success/fail, which service, how many retries

2. Run PLANTE 5 times WITH pivot feature
   - Record: same metrics + pivot count

3. Compare results
```

---

## Success Criteria

The feature is successful if:

1. **Pivot happens**: System actually tries different service after FUNDAMENTAL failure
2. **Success rate improves**: Measurable increase from baseline
3. **Fewer wasted retries**: System stops retrying impossible exploits faster
4. **Works on multiple VMs**: Not just Metasploitable 2

---

## What To Tell Professor

> "I implemented adaptive failure handling for PLANTE. When an exploit fails, the system now:
>
> 1. **Investigates** - runs diagnostic commands to verify why it failed
> 2. **Classifies** - uses evidence (not guessing) to determine if fixable
> 3. **Pivots** - if unfixable, automatically tries a different vulnerability
>
> Tested on Metasploitable 2 and Kioptrix. Success rate improved from X% to Y%."

---

## Files Changed

```
PLANTE/
├── agents/
│   ├── orchestrator.py    # MODIFY: Add investigate + pivot + new main loop
│   └── classifier.py      # MODIFY: Accept evidence parameter
├── docs/
│   └── ATLAS_plan.md      # This file
└── results/
    └── pivot_benchmark/   # NEW: Before/after test results
```

---

## Removed From Original Plan (Too Complex)

- ~~5 specialized agents~~ → Keep single orchestrator
- ~~Knowledge base with learning~~ → Not needed for pivot
- ~~8 week timeline~~ → Can finish in 1-2 weeks
- ~~10 benchmark challenges~~ → 2 VMs is enough
- ~~Coordinator agent~~ → Existing orchestrator works fine
- ~~Cross-run learning~~ → Out of scope

---

## Summary

**Simple version:**
1. When exploit fails, check if port/service/module actually exist
2. If problem is fundamental (wrong version, no module), try different service
3. Measure improvement

That's it. No multi-agent architecture needed.
