# Setup Instructions 
## Create a Supabase Account 
- Go to supabase.com
- Sign up for a free account
- Create a new project

## Enable IPv4 Session Pooler Supabase free tier projects are IPv6-only by default. To connect from most systems: 
- Click Connect
- Select Session Pooler under methods
- Copy the connection details (host, port, user, password)
- Add DB Config details in env based on .env.example

Run Database schema in Supabase SQL Editor
-- ============================================================
-- TRACK OVERALL ATTACK RUNS (SESSION-LEVEL)
-- ============================================================
CREATE TABLE attack_runs (
  run_id SERIAL PRIMARY KEY,
  started_at TIMESTAMP DEFAULT NOW(),
  ended_at TIMESTAMP,
  target_ip TEXT,
  target_os TEXT,
  status TEXT CHECK (status IN ('running','completed','failed')),
  description TEXT
);

-- ============================================================
-- REGISTER ACTIVE AGENTS (ORCHESTRATOR, RECON, ATTACK, ETC.)
-- ============================================================
CREATE TABLE agents (
  agent_id SERIAL PRIMARY KEY,
  name TEXT,             -- e.g. 'Orchestrator', 'ReconAgent'
  type TEXT,             -- e.g. 'coordinator', 'recon', 'attack'
  ip_address TEXT,
  status TEXT,
  last_seen TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- COMMAND EXECUTION LOGS (PRIMARY TELEMETRY SOURCE)
-- ============================================================
CREATE TABLE commands (
  command_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  agent_id INT REFERENCES agents(agent_id),
  source TEXT,                -- 'procedure', 'websearch', 'redstack', 'manual'
  tool_name TEXT,             -- e.g. 'nmap', 'nikto', 'gobuster'
  command_text TEXT,
  target_ip TEXT,
  started_at TIMESTAMP DEFAULT NOW(),
  ended_at TIMESTAMP,
  duration_seconds FLOAT,
  success BOOLEAN,
  exit_code INT,
  response_time_ms INT,       -- latency metric (optional telemetry)
  error_message TEXT,
  raw_output TEXT             -- complete output for later parsing
);

-- ============================================================
-- RECONNAISSANCE RESULTS
-- ============================================================
CREATE TABLE recon_results (
  recon_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  command_id INT REFERENCES commands(command_id),
  agent_id INT REFERENCES agents(agent_id),
  target_ip TEXT,
  tool_used TEXT,
  result_json JSONB,          -- structured scan data
  raw_output TEXT,            -- original unparsed tool output
  created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ATTACK CHAIN PLANNING (RAG / CORRELATION PHASE)
-- ============================================================
CREATE TABLE attack_chains (
  chain_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  recon_id INT REFERENCES recon_results(recon_id),
  attack_surface TEXT,
  proposed_stages JSONB,      -- structured 3-phase chain
  chain_json JSONB,
  mitre_attack_ids TEXT[],    -- list of MITRE ATT&CK references
  created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- LLM DECISIONS AND PROMPT/RESPONSE LOGGING
-- ============================================================
CREATE TABLE llm_decisions (
  decision_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  command_id INT REFERENCES commands(command_id),
  llm_model TEXT,             -- 'openrouter/gpt-4', 'AnythingLLM', etc.
  prompt TEXT,
  response TEXT,
  reasoning TEXT,
  tokens_used INT,
  response_time_ms INT,       -- telemetry for LLM latency
  created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- VULNERABILITIES DISCOVERED
-- ============================================================
CREATE TABLE vulnerabilities (
  vuln_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  recon_id INT REFERENCES recon_results(recon_id),
  target_ip TEXT,
  port INT,
  service_name TEXT,
  service_version TEXT,
  vulnerability_type TEXT,
  severity TEXT CHECK (severity IN ('critical','high','medium','low')),
  cve_id TEXT,
  description TEXT,
  mitre_attack_id TEXT,
  discovered_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- RAW LOGS / DEBUG / FALLBACK STORAGE
-- ============================================================
CREATE TABLE raw_logs (
  log_id SERIAL PRIMARY KEY,
  run_id INT REFERENCES attack_runs(run_id) ON DELETE CASCADE,
  source TEXT,               -- 'kali_mcp', 'orchestrator', 'anythingllm'
  log_level TEXT,            -- 'INFO', 'WARN', 'ERROR'
  message TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
