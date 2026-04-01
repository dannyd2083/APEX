#!/usr/bin/env python3
"""Patch kali_api_server.py to add hidden_fields support."""

with open('/home/kali/MCP-Kali-Server/kali_api_server.py', 'r') as f:
    content = f.read()

# New function using double-pass (no mixed quote issues)
NEW_FUNC = '''
def _extract_hidden_fields(html):
    """Return all hidden form fields as {name: value} — works for any framework."""
    import re as re2
    fields = {}
    # Two passes: double-quoted then single-quoted attributes
    for m in re2.finditer(r'<input[^>]+type="hidden"[^>]*>', html, re2.I):
        tag = m.group(0)
        nm = re2.search(r'name="([^"]*)"', tag)
        vm = re2.search(r'value="([^"]*)"', tag)
        if nm:
            fields[nm.group(1)] = vm.group(1) if vm else ""
    for m in re2.finditer(r"<input[^>]+type='hidden'[^>]*>", html, re2.I):
        tag = m.group(0)
        nm = re2.search(r"name='([^']*)'", tag)
        vm = re2.search(r"value='([^']*)'", tag)
        if nm and nm.group(1) not in fields:
            fields[nm.group(1)] = vm.group(1) if vm else ""
    return fields
'''

# Insert after _extract_csrf function (before "import threading")
INSERT_BEFORE = "import threading"
if INSERT_BEFORE in content:
    content = content.replace(INSERT_BEFORE, NEW_FUNC + "\n" + INSERT_BEFORE, 1)
    print("Step 1 OK: _extract_hidden_fields added")
else:
    print("ERROR: insertion point not found")

# Add hidden_fields to http_get response
OLD_RESP = '''        return jsonify({"status": r.status_code, "url": r.url,
                        "text": r.text[:50000], "csrf_token": csrf_token,
                        "session_expired": session_expired})'''
NEW_RESP = '''        hidden_fields = _extract_hidden_fields(r.text)
        return jsonify({"status": r.status_code, "url": r.url,
                        "text": r.text[:50000], "csrf_token": csrf_token,
                        "hidden_fields": hidden_fields,
                        "session_expired": session_expired})'''
if OLD_RESP in content:
    content = content.replace(OLD_RESP, NEW_RESP)
    print("Step 2 OK: hidden_fields added to http_get response")
else:
    print("ERROR: http_get response pattern not found")

with open('/home/kali/MCP-Kali-Server/kali_api_server.py', 'w') as f:
    f.write(content)
print("Done")
