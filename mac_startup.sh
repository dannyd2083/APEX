#!/bin/bash

# =============================================
# Project Startup Script – with .env support
# =============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
[[ -f "$ENV_FILE" ]] && export $(grep -v '^#' "$ENV_FILE" | xargs)

: "${ANYTHINGLLM_APP_NAME:=AnythingLLM}"
: "${KALI_VM_NAME:?Error: KALI_VM_NAME must be set in .env file!}"
: "${METASPLOITABLE_VM_NAME:?Error: METASPLOITABLE_VM_NAME must be set in .env file!}"
: "${KALI_IP:?Error: KALI_IP must be set in .env file!}"
: "${KALI_USER:=kali}"
: "${MCP_START_COMMAND:?Error: MCP_START_COMMAND must be set in .env file!}"
: "${VM_MODE:=gui}"

echo "Starting full lab environment..."

# 1. Open AnythingLLM
open -a "$ANYTHINGLLM_APP_NAME" && echo "✓ AnythingLLM launched"

# 2. Start Kali VM
VBoxManage startvm "$KALI_VM_NAME" --type "$VM_MODE"
echo "✓ Kali VM started"

# # Wait for Kali SSH
# echo "Waiting for Kali server to come online on port 5000..."
# for i in {1..60}; do
#     nc -z "$KALI_IP" 5000 2>/dev/null && { echo "Kali server ready after $((i*2))s"; break; }
#     [ $i -eq 60 ] && { echo "ERROR: Kali server never started"; exit 1; }
#     sleep 2
# done

# 3. Start Metasploitable
VBoxManage startvm "$METASPLOITABLE_VM_NAME" --type "$VM_MODE"
echo "✓ Metasploitable started"

# ────── EVERYTHING IS READY NOW ──────
echo ""
echo "══════════════════════════════════════"
echo "   ALL VMs AND SERVICES ARE UP!      "
echo "   Starting MCP server (foreground)   "
echo "══════════════════════════════════════"
echo ""

# 4. FINALLY start MCP server in foreground → terminal stays here
exec bash -c "$MCP_START_COMMAND"