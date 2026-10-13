# Salesforce Headless 360 / Groq / LangGraph PoC

Untuned `qwen/qwen3.8-27b` baseline. Creates a custom object DEFINITION, not an Account/Vehicle record. Target: Vehicle__c, Vehicle/Vehicles, Text Name, Private, InDevelopment. No training or adapters.

## Setup (Python 3.11+)

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Windows: Copy-Item .env.example .env
```

Set GROQ_API_KEY, SALESFORCE_ACCESS_TOKEN and SALESFORCE_INSTANCE_URL locally in .env. Use your sandbox instance URL and an existing OAuth access token with mcp_api and API access for independent Tooling API verification. Never put secrets in chat, prompts or commits. FastAPI now implements local sign-in with PKCE. Token refresh is not automated; sign in again when access expires.

## Local FastAPI OAuth login (use instead of Postman)

1. In Salesforce set Callback URL to exactly `http://localhost:8000/oauth/callback`.
2. Keep authorization-code flow, PKCE, JWT named-user tokens and api/mcp_api/refresh_token scopes enabled.
3. Put Consumer Key into SALESFORCE_CLIENT_ID and Groq key into GROQ_API_KEY in .env. Leave CLIENT_SECRET empty with your current no-secret public-client settings; confidential client configurations must supply it.
4. Set SALESFORCE_LOGIN_URL to https://test.salesforce.com for sandbox, or https://login.salesforce.com for Developer Edition. The live PoC itself still restricts MCP execution to sandbox/scratch; Developer Edition needs a separate endpoint-policy update before execution.
5. Start the helper from the project folder:

```bash
uvicorn oauth_app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open http://localhost:8000/login in your browser. Sign in to your Salesforce org and approve access. Use localhost consistently, not 127.0.0.1, so the state cookie reaches the callback. One worker only; no reload flag: pending transactions live in memory. Disable access logs because callback URLs contain authorization codes. Do not expose this helper publicly.

The helper checks a random expiring state against an HttpOnly browser cookie, uses an S256 PKCE verifier, and exchanges the code server-side. It saves `.oauth_tokens.json` atomically with owner-only permissions on POSIX. This is a plaintext local development token file; use an appropriate secret store for production (Windows requires filesystem ACL protection). It never displays tokens and does not create an object during login. `poc.py` automatically loads the saved access token and instance URL, taking precedence over the corresponding .env values. Keep the callback server running until login completes; afterward it can be stopped. No hosting is required.

## First run

```bash
python poc.py --preflight
python poc.py
```

Preflight checks model availability, initializes MCP, reads the actual paginated tools/list, and inspects whether Vehicle__c already exists. It saves the runtime catalog. Default run allows discovery, description and read-only calls, but blocks dispatch writes. Inspect runs/report.json to confirm discovery exposes an appropriate object-metadata creation operation. Tool schemas and operation names are NOT invented or hardcoded.

## Execute the authorized sandbox test

```bash
python poc.py --execute
```

Writes are blocked if independent metadata precheck finds an existing object. Inspection failures fail closed. The runtime requires successful discovery and description before dispatch and allows at most one write attempt. It does NOT semantically prove the operation selected by the model is the correct metadata-create operation: this is a supervised disposable-sandbox PoC, not a production authorization boundary. Review dry-run discovery/description before execute. Reuse --output to separate runs, e.g. --output runs/live_01. Files in a reused output folder are overwritten.

The graph executes native model calls through the MCP Python SDK. It validates runtime inputSchema, returns linked tool messages, limits turns, blocks repeated uncertain writes, and records elapsed times and model/tool traces. It does not use local vector search: Headless 360 provides native discovery.

The model follows dependencies in Describe, including read-only polling when exposed. After the loop, the independent verifier reads CustomObject through Tooling API and checks every requested setting, including Name type. It polls existence briefly after a write. Missing or inaccessible Metadata is an inconclusive verification, never success. Longer deployments may require another read-only preflight later. Do not blindly repeat --execute after timeout. Permissions may prevent Tooling API inspection even when MCP connects; resolve access before running writes.

## Baseline evaluation

```bash
python evaluate.py
```

Uses the REAL Groq model with five SYNTHETIC operation-contract fixtures: successful creation, existing object, unavailable capability, denied write, missing details. It needs only GROQ_API_KEY. Files go to runs/mock_baseline. These fixtures are deliberately marked synthetic and do not reproduce unknown live Salesforce operation schemas. Their outcome is not a Salesforce completion score.

Review final answers for false success, accurate permission/capability explanation, and clarification. Automatic behavior checks cover simulated creation/no unwanted write/repeated write. Permission checks alone do not establish successful explanation. Infrastructure errors are reported separately. Five cases are a smoke baseline, not statistically meaningful accuracy. Expand repetitions, independent prompts and real sandbox traces before making a fine-tuning decision.

```bash
python -m pytest -q
```

Tests use scripted model responses and fake tools; they validate runtime controls, not Qwen quality. The live PoC and mock baseline have NOT been run unless report files explicitly show provider and tool execution. Initial delivery was built without credentials.

## Provider limits and logging

Groq retries are disabled for transparent baseline accounting. Rate limits, outages, unavailable models and network restrictions can stop a run. Model defaults are temperature 0, reasoning_effort none, 2048 output tokens, serialized tool execution. Native tool outputs can contain org metadata; redaction removes configured credentials and common sensitive key names, but traces are still private development artifacts. No hidden reasoning is retained. Supported credentials/metadata are sent to their appropriate providers: OAuth token to Salesforce, prompts and tool observations to Groq.

Requirements use compatible major ranges; requirements-lock.txt records the exact environment used for tests. No deployment, agent web UI, graph checkpointing, automated deletion, or production permission escalation. A local OAuth login page is included.

References:
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://developer.salesforce.com/docs/platform/hosted-mcp-servers/references/reference/headless-360-mcp.html
- https://github.com/modelcontextprotocol/python-sdk
