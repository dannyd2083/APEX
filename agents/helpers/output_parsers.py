"""
Structured output parsers for recon tools.

These replace LLM interpretation for tools that produce structured output.
Each parser returns a list of finding dicts: {type, value, confidence, evidence}
"""
from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# nmap
# ---------------------------------------------------------------------------

def parse_nmap(raw: str) -> list[dict]:
    findings = []

    # Open ports + service/version
    # e.g. "80/tcp   open  http    Apache httpd 2.4.38"
    for m in re.finditer(r'(\d+)/(tcp|udp)\s+open\s+(\S+)\s*(.*)', raw):
        port, proto, service, version = m.groups()
        version = version.strip()
        value = f"{service} on port {port}/{proto}"
        if version:
            value += f" ({version})"
        findings.append({
            "type": "service",
            "value": value,
            "confidence": "high",
            "evidence": f"nmap: {port}/{proto} open {service} {version}".strip(),
        })

    # http-title
    for m in re.finditer(r'http-title:\s*(.+)', raw):
        title = m.group(1).strip()
        skip = {"Did not follow redirect", "400 Bad Request",
                "403 Forbidden", "301 Moved Permanently", ""}
        if title not in skip:
            findings.append({
                "type": "service",
                "value": f"HTTP title: {title}",
                "confidence": "medium",
                "evidence": f"nmap http-title: {title}",
            })

    # http-auth-finder
    for m in re.finditer(r'http-auth-finder:.*?(\w+ \w+)\s*$', raw, re.MULTILINE):
        findings.append({
            "type": "auth",
            "value": f"HTTP auth required: {m.group(1).strip()}",
            "confidence": "high",
            "evidence": "nmap http-auth-finder",
        })

    # vuln scripts — CVE hits
    for m in re.finditer(r'CVE-(\d{4}-\d+).*?State:\s*(VULNERABLE[^\n]*)', raw, re.DOTALL):
        cve, state = m.groups()
        findings.append({
            "type": "vulnerability",
            "value": f"CVE-{cve} — {state.strip()[:80]}",
            "confidence": "high",
            "evidence": f"nmap vuln script: CVE-{cve}",
        })

    # Generic "VULNERABLE" lines from vuln scripts without explicit CVE
    for m in re.finditer(r'\|\s+([\w\s\-]+):\s*\n\s*\|\s+State:\s*(VULNERABLE)', raw):
        name = m.group(1).strip()
        if "CVE" not in name:
            findings.append({
                "type": "vulnerability",
                "value": f"Vulnerability: {name}",
                "confidence": "high",
                "evidence": f"nmap vuln script: {name} VULNERABLE",
            })

    return _dedup(findings)


# ---------------------------------------------------------------------------
# gobuster
# ---------------------------------------------------------------------------

def parse_gobuster(raw: str) -> list[dict]:
    findings = []
    INTERESTING = {200, 204, 301, 302, 307, 401, 403}

    for m in re.finditer(r'(/\S+)\s+\(Status:\s*(\d+)\)', raw):
        path, status_str = m.groups()
        status = int(status_str)
        if status not in INTERESTING:
            continue
        confidence = "high" if status in (200, 204, 301, 302, 307) else "medium"
        findings.append({
            "type": "directory",
            "value": f"{path} [HTTP {status}]",
            "confidence": confidence,
            "evidence": f"gobuster: {path} returned {status}",
        })

    return _dedup(findings)


# ---------------------------------------------------------------------------
# ZAP active scan alerts
# ---------------------------------------------------------------------------

def parse_zap_alerts(raw: str) -> list[dict]:
    findings = []
    RISK_TO_CONF = {"High": "high", "Medium": "medium", "Low": "low",
                    "Informational": "low", "Info": "low"}

    # The KaliMCP.zap_active() output is:  scan_out + "\n\n[ZAP ALERTS]\n" + alerts_out
    # Extract everything after [ZAP ALERTS]
    alerts_section = raw
    split = raw.split("[ZAP ALERTS]", 1)
    if len(split) == 2:
        alerts_section = split[1]

    # Try JSON array
    json_m = re.search(r'\[\s*\{.+\}\s*\]', alerts_section, re.DOTALL)
    if json_m:
        try:
            alerts = json.loads(json_m.group(0))
            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                name  = alert.get("alert") or alert.get("name", "Unknown alert")
                risk  = (alert.get("risk") or alert.get("riskdesc", "Medium")).split()[0]
                url   = alert.get("url", "")
                param = alert.get("param", "")
                evid  = alert.get("evidence", "")

                value = name
                if url:
                    value += f" at {url}"
                if param:
                    value += f" (param: {param})"

                ev_str = f"ZAP: {name}"
                if evid:
                    ev_str += f" | {evid[:120]}"

                findings.append({
                    "type": "vulnerability",
                    "value": value,
                    "confidence": RISK_TO_CONF.get(risk, "medium"),
                    "evidence": ev_str,
                })
            return _dedup(findings)
        except (json.JSONDecodeError, Exception):
            pass

    # Fallback: text format "Alert: ...\nRisk: ...\nURL: ..."
    for block in re.split(r'\n(?=Alert:)', alerts_section):
        name_m  = re.search(r'Alert:\s*(.+)',     block)
        risk_m  = re.search(r'Risk:\s*(.+)',      block)
        url_m   = re.search(r'URL:\s*(.+)',       block)
        param_m = re.search(r'Parameter:\s*(.+)', block)
        if not name_m:
            continue
        name  = name_m.group(1).strip()
        risk  = (risk_m.group(1).strip().split()[0] if risk_m else "Medium")
        url   = url_m.group(1).strip()   if url_m   else ""
        param = param_m.group(1).strip() if param_m else ""

        value = name
        if url:
            value += f" at {url}"
        if param:
            value += f" (param: {param})"

        findings.append({
            "type": "vulnerability",
            "value": value,
            "confidence": RISK_TO_CONF.get(risk, "medium"),
            "evidence": f"ZAP: {name}",
        })

    return _dedup(findings)


# ---------------------------------------------------------------------------
# zap spider — extract discovered URLs
# ---------------------------------------------------------------------------

def parse_zap_spider(raw: str) -> list[dict]:
    findings = []
    SKIP = {"(no URLs found)", ""}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line in SKIP:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            findings.append({
                "type": "directory",
                "value": line,
                "confidence": "high",
                "evidence": f"ZAP spider: {line}",
            })
    return _dedup(findings)


# ---------------------------------------------------------------------------
# autorecon — routes file sections to nmap/gobuster/whatweb parsers
# ---------------------------------------------------------------------------

def parse_autorecon(raw: str) -> list[dict]:
    findings = []

    # Our kali_bridge produces: "--- /path/to/file.txt ---\n<content>\n--- ...\n"
    parts = re.split(r'--- (.+?) ---\n', raw)

    i = 1
    while i + 1 < len(parts):
        filename = parts[i].lower()
        content  = parts[i + 1]
        i += 2

        if "nmap" in filename:
            findings.extend(parse_nmap(content))
        elif "gobuster" in filename or "feroxbuster" in filename:
            findings.extend(parse_gobuster(content))
        elif "whatweb" in filename:
            findings.extend(parse_whatweb(content))

    # If no file sections parsed (e.g. autorecon timed out, output is just logs),
    # fall back to trying nmap/gobuster on the whole output
    if not findings:
        findings.extend(parse_nmap(raw))
        findings.extend(parse_gobuster(raw))

    return _dedup(findings)


# ---------------------------------------------------------------------------
# whatweb
# ---------------------------------------------------------------------------

def parse_whatweb(raw: str) -> list[dict]:
    findings = []

    # Status line: "Status    : 200 OK"
    status_m = re.search(r'Status\s*:\s*(\d+)', raw)
    if not status_m or status_m.group(1) != "200":
        return findings

    # Title
    title_m = re.search(r'Title\s*:\s*(.+)', raw)
    if title_m:
        findings.append({
            "type":       "service",
            "value":      f"HTTP title: {title_m.group(1).strip()}",
            "confidence": "high",
            "evidence":   "whatweb",
        })

    # Email addresses
    for m in re.finditer(r'String\s*:\s*([\w.+-]+@[\w.-]+\.\w+)', raw):
        findings.append({
            "type":       "credential",
            "value":      f"Email found: {m.group(1).strip()}",
            "confidence": "medium",
            "evidence":   "whatweb email extraction",
        })

    # CMS / framework (WordPress, Joomla, Drupal, etc.)
    for cms in ("WordPress", "Joomla", "Drupal", "Magento", "Laravel",
                "Django", "Rails", "jQuery", "Bootstrap"):
        if cms.lower() in raw.lower():
            findings.append({
                "type":       "service",
                "value":      f"Framework/CMS detected: {cms}",
                "confidence": "medium",
                "evidence":   "whatweb",
            })

    # Server version from HTTPServer plugin
    server_m = re.search(r'String\s*:\s*(Apache[\w/. ()]+|nginx[\w/. ()]+|IIS[\w/. ()]+)', raw)
    if server_m:
        findings.append({
            "type":       "service",
            "value":      f"Web server: {server_m.group(1).strip()}",
            "confidence": "high",
            "evidence":   "whatweb HTTPServer",
        })

    return _dedup(findings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup(findings: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in findings:
        key = f["value"]
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
