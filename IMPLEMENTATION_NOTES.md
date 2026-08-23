# ParcelPilot Assist

AI support and operations system for the **CalQuity ParcelPilot AI Agent Assessment**.

Full planning: [`ParcelPilot_Assessment_Plan.md`](ParcelPilot_Assessment_Plan.md)

## Monorepo layout

```text
apps/
  api/          FastAPI + LangGraph agent (Groq LLM, Gemini embeddings)
  web/          Next.js chat + ops dashboard
data/           Candidate PDFs + xlsx
docs/           Architecture & product notes
packages/shared Shared types (later)
tests/golden/   Golden eval scenarios
```

## Split-provider stack

| Workload | Provider |
|----------|----------|
| Agent LLM | **Groq** (`openai/gpt-oss-20b`) |
| Embeddings | **Gemini** (`gemini-embedding-001`, 768-dim) |
| Structured data | **PostgreSQL** |
| Vectors | **ChromaDB** |

## Quick start — API

```powershell
cd apps/api
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Edit .env with your keys and DATABASE_URL

uvicorn app.main:app --reload --port 8000
```

Health check: http://localhost:8000/health

Run tests:

```powershell
cd apps/api
.venv\Scripts\activate
pytest
```

## Quick start — Web

Requires Node.js 20+.

```powershell
cd apps/web
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:3000 (shows API status when backend is running).

## Environment variables

See [`apps/api/.env.example`](apps/api/.env.example) and [`apps/web/.env.example`](apps/web/.env.example).

## Data snapshot

All time-based logic uses **`2026-08-16 11:00 Asia/Kolkata`** (see `data/ParcelPilot_Assessment_Data.xlsx` README sheet).

## Implementation status

- [x] Phase A1 — Monorepo scaffold + requirements.txt
- [x] Phase A2 — Data pack in `data/`
- [x] Phase A3 — PostgreSQL ingest (models, registry, ingest CLI, `/data/stats`)
- [x] Phase A4 — Snapshot clock helper (`app/timeutil.py`)
- [x] Phase A5–A7 — PDF chunking, Chroma + Gemini embed, `document_search`
- [x] Phase B1 — JWT mock auth + personas (`/auth/login`, `/auth/me`)
- [x] Phase B2 — ACL on tools (`app/auth/acl.py`; search requires JWT + account scope)
- [x] Phase B4 — `structured_data_query` lookups (account/order/ticket + ACL)
- [x] Phase B5 — Cancellation calculator (`calc_cancellation`)
- [x] Phase B6 — Service credit calculator (`calc_service_credit`)
- [x] Phase B7 — SLA calculator (`calc_sla`)
- [x] Phase B8 — Pending action + confirm/cancel APIs
- [x] Phase C1 — LangGraph agent + `/chat` (tools + history)
- [x] Phase C2 — Trust synthesis (confidence, conflicts, citations)
- [x] Phase C3 — HITL interrupt (`/chat` pause + `/chat/resume`)
- [x] Phase C4 — Agent write tools: escalate / update_ticket / follow-up
- [x] Phase C5 — Streaming tool events (`/chat/stream` + live tool chips in UI)
- [ ] Phase D — Chat UI polish (citations/confirm already scaffolded in C5)
- [ ] Phase E — Proactive dashboard + eval harness
- [ ] Phase F — Deploy + submission docs

## Phase A3 — Database ingest (Supabase)

### Step 1 — Configure `DATABASE_URL`

In `apps/api/.env`, set your Supabase connection string (URL-encode special characters in the password):

```env
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require
```

### Step 2 — Create tables and load data

```powershell
cd apps/api
.venv\Scripts\activate   # or your Python env with requirements installed
python -m app.ingest
```

Expected output:

```text
accounts: 4
orders: 6
tickets: 7
documents: 6
```

This loads:

- **Excel** → `accounts`, `orders`, `tickets`
- **PDF registry** → `documents` (metadata for Chroma ingest in A5–A7)

Re-running ingest is **idempotent** (`merge` upserts).

### Step 3 — Verify

```powershell
# API running:
uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000/data/stats — row counts
- Supabase **Table Editor** — inspect tables

### Tables

| Table | Source |
|-------|--------|
| `accounts` | Excel `accounts` sheet |
| `orders` | Excel `orders` sheet |
| `tickets` | Excel `tickets` sheet |
| `documents` | Curated registry (`app/ingest/document_registry.py`) |

Snapshot clock for all time logic: **`app/timeutil.py`** → `2026-08-16 11:00 Asia/Kolkata`

## Phase A5–A7 — Chroma vector ingest + document search

### Step 1 — Set `GEMINI_API_KEY`

In `apps/api/.env`:

```env
GEMINI_API_KEY=your_key
CHROMA_PATH=./.chroma
```

### Step 2 — Index PDFs into Chroma

```powershell
cd apps/api
.venv\Scripts\activate
python -m app.ingest.chroma
```

Expected: **23 chunks** across 6 PDFs (section-aware chunking per `docs/RAG_APPROACH.md`).

### Step 3 — Search API

With the API running:

```powershell
# GET
curl "http://localhost:8000/search/documents?q=enterprise%20P1%20response%20time"

# POST (with filters)
curl -X POST http://localhost:8000/search/documents ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"cancellation fee\", \"doc_types\": [\"policy\"]}"
```

Deprecated v2 policy is indexed but **excluded by default** (`include_deprecated=false`). Pass `"include_deprecated": true` to include it.

### Key modules

| Module | Role |
|--------|------|
| `app/ingest/pdf_chunker.py` | Section-aware PDF chunking |
| `app/embeddings/gemini.py` | Gemini `gemini-embedding-001` (768-dim) |
| `app/vector/chroma_store.py` | Chroma client + metadata filters |
| `app/tools/document_search.py` | Retrieval tool (agent-ready) |
| `app/routes/search.py` | HTTP search endpoints |

## Phase B1 — Mock auth (JWT + personas)

No passwords — pick a demo persona and get a JWT.

```powershell
# List personas
curl.exe http://localhost:8000/auth/personas

# Login as Northstar customer
curl.exe -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"persona_id\":\"northstar\"}"

# Who am I?
curl.exe http://localhost:8000/auth/me -H "Authorization: Bearer <token>"
```

| Persona id | Role | Account |
|------------|------|---------|
| `northstar` | customer | ACCT-001 |
| `lumenworks` | customer | ACCT-002 |
| `beacon` | customer | ACCT-003 |
| `axis` | customer | ACCT-004 |
| `maya` | support_agent | (all) |
| `ops` | ops_admin | (all) + dashboard |

JWT claims: `role`, `account_id`, `user_id`, `name`, `persona_id`. Config: `JWT_SECRET`, `JWT_EXPIRE_MINUTES`.

## Phase B2 — ACL (account scope)

Search now **requires a Bearer token**. Customers are forced to their own `account_id`; internal roles can query any account.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"northstar"}').access_token

# OK — scoped to ACCT-001 + global policies
curl.exe "http://localhost:8000/search/documents?q=P1%20response" -H "Authorization: Bearer $token"

# 403 — Northstar cannot query LumenWorks
curl.exe "http://localhost:8000/search/documents?q=P1&account_id=ACCT-002" -H "Authorization: Bearer $token"
```

| Helper | Purpose |
|--------|---------|
| `resolve_account_scope` | Customer → own account; internal → optional filter |
| `assert_account_access` | Block cross-account resource reads |
| `scope_document_search` | Apply account filter + block deprecated for customers |

## Phase B4 — Structured data lookups

Parameterized Postgres queries (no raw SQL). Requires Bearer token + ACL.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"northstar"}').access_token

# Own order — OK
Invoke-RestMethod -Method POST -Uri http://localhost:8000/tools/structured_data `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"intent":"get_order","order_id":"ORD-1001"}'

# Other company's order — 403
Invoke-RestMethod -Method POST -Uri http://localhost:8000/tools/structured_data `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"intent":"get_order","order_id":"ORD-2001"}'
```

| Intent | Params |
|--------|--------|
| `get_account` | `account_id?` (customer → own) |
| `get_order` | `order_id` |
| `list_orders` | `account_id?`, `status?` |
| `get_ticket` | `ticket_id` |
| `list_tickets` | `account_id?`, `status?` |

Calculators (`calc_cancellation`, etc.) come in B5–B7.

## Phase B5 — Cancellation calculator

Deterministic Python rules (SOP + Northstar agreement override). Not LLM math.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"northstar"}').access_token

Invoke-RestMethod -Method POST -Uri http://localhost:8000/tools/structured_data `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"intent":"calc_cancellation","order_id":"ORD-1001"}'
```

| Order | Expected |
|-------|----------|
| ORD-1001 (Northstar BOOKED 120 min) | allowed, fee ₹0 (agreement waives SOP ₹250) |
| ORD-2001 (LumenWorks BOOKED 75 min) | allowed, fee ₹250 |
| ORD-3001 (Beacon within 30 min) | allowed, fee ₹0 |
| ORD-1002 (PICKED_UP) | not allowed → RTO |
| ORD-4001 (DELIVERED) | not allowed |

## Phase B6 — Service credit calculator

Failed-pickup credit from SOP + LumenWorks override. Uses snapshot clock vs `pickup_window_end`.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"lumenworks"}').access_token

$result = Invoke-RestMethod -Method POST -Uri http://localhost:8000/tools/structured_data `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"intent":"calc_service_credit","order_id":"ORD-2002"}'

$result.data | ConvertTo-Json -Depth 5
```

| Case | Expected |
|------|----------|
| ORD-2002 (LumenWorks, 4.5h late, carrier fault) | eligible, **INR 300** (agreement; SOP would be 240) |
| No `carrier_fault` | not eligible, `abstain=true` |
| Credit > INR 1000 | `needs_manager_approval=true` |

## Phase B7 — SLA calculator

First-response SLA vs snapshot clock. Severity from ticket text (or optional `severity` override). Agreement overrides policy defaults.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"maya"}').access_token

$result = Invoke-RestMethod -Method POST -Uri http://localhost:8000/tools/structured_data `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"intent":"calc_sla","ticket_id":"TKT-501"}'

$result.data | ConvertTo-Json -Depth 5
```

| Ticket | Expected |
|--------|----------|
| TKT-501 (Northstar outage) | P1, target **15 min**, elapsed 30, **breached** |
| TKT-505 (API key / Axis Enterprise) | P1, target **30 min**, elapsed 150, **breached** |
| TKT-503 (billing how-to) | P3 |

## Phase B8 — Confirm before mutate

State-changing actions create a **pending** record first. Nothing is written to escalations/tasks until confirm.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"maya"}').access_token

# 1) Propose escalation (no ESC row yet)
$pending = Invoke-RestMethod -Method POST -Uri http://localhost:8000/actions/escalate `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"ticket_id":"TKT-501","severity":"P1","reason":"SLA breached","recommended_next_step":"Page on-call"}'

$pending | ConvertTo-Json -Depth 5
$id = $pending.pending_action.pending_id

# 2a) Confirm → creates escalations row + audit
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/actions/$id/confirm" `
  -Headers @{ Authorization = "Bearer $token" }

# 2b) Or cancel → no mutation
# Invoke-RestMethod -Method POST -Uri "http://localhost:8000/actions/$id/cancel" -Headers @{ Authorization = "Bearer $token" }
```

| Endpoint | Effect |
|----------|--------|
| `POST /actions/escalate` | Propose only (`needs_confirmation=true`) |
| `POST /actions/propose` | Same for escalate / update_ticket / follow-up task |
| `POST /actions/{id}/confirm` | Execute + audit |
| `POST /actions/{id}/cancel` | Discard; no DB mutation |

## Phase C1 — Chat agent (LangGraph + Groq)

Multi-step tool-calling agent. Requires `GROQ_API_KEY` and Bearer JWT.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"northstar"}').access_token

$result = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"message":"Can I cancel ORD-1001 without a fee?"}'

$result | ConvertTo-Json -Depth 6

# Continue the same conversation:
$thread = $result.thread_id
Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body "{`"message`":`"What document did you use?`",`"thread_id`":`"$thread`"}"
```

| Piece | Role |
|-------|------|
| `app/agent/graph.py` | LangGraph ReAct loop + in-memory `thread_id` history |
| `app/agent/tools.py` | Binds search, structured data, escalate-propose |
| `app/agent/prompts.py` | System instructions + doc catalog |
| `POST /chat` | One turn; returns `answer` + `tools_used` |

## Phase C2 — Trust synthesis

After the agent answers, a **deterministic** trust node inspects tool JSON (not another LLM guess) and attaches:

- `confidence` (`high` / `medium` / `low`)
- `conflicts[]` (e.g. agreement fee ₹0 vs SOP ₹250)
- `citations[]` from calculators / search
- flags: abstain, recommend_escalation, needs_confirmation, …

If the model forgot to mention a conflict, a short **Trust note** is appended to `answer`.

```powershell
# Same /chat call — look at .trust in the response
$result.trust | ConvertTo-Json -Depth 6
```

## Phase C3 — Confirmation interrupt (HITL)

When the agent calls `create_escalation`, LangGraph **pauses** the thread. Nothing is written to escalations until you resume with confirm.

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"maya"}').access_token

$paused = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"message":"Escalate TKT-501 as P1 — SLA breached. Page on-call. Use create_escalation."}'

$paused.status          # awaiting_confirmation
$paused.draft           # ticket_id / severity / reason (not executed yet)
$thread = $paused.thread_id

# Confirm (creates escalation) or cancel (no DB write)
$done = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat/resume `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body "{`"thread_id`":`"$thread`",`"decision`":`"confirm`"}"

$done.status            # completed
$done.answer
```

| Piece | Role |
|-------|------|
| `interrupt()` in `create_escalation` | Pauses after drafting; DB write only on confirm resume |
| `POST /chat` | May return `status=awaiting_confirmation` + `draft` |
| `POST /chat/resume` | `{ thread_id, decision: confirm\|cancel }` continues the same thread |

## Phase C4 — Update ticket & follow-up (agent tools)

Same HITL gate as escalation. Agent tools:

| Tool | Effect after confirm |
|------|----------------------|
| `create_escalation` | Inserts `escalations` row |
| `update_ticket` | Updates status / assignee / appends notes |
| `create_follow_up_task` | Inserts `follow_up_tasks` row |

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"maya"}').access_token

# Update ticket notes
$paused = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"message":"Use update_ticket on TKT-504. Append notes: called carrier. Do not change status."}'

$paused.action_type   # update_ticket
$paused.status        # awaiting_confirmation

$done = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat/resume `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body "{`"thread_id`":`"$($paused.thread_id)`",`"decision`":`"confirm`"}"

# Follow-up task (cancel = no DB row)
$paused2 = Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"message":"Use create_follow_up_task. Title: Call carrier. ticket_id TKT-502."}'

Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat/resume `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body "{`"thread_id`":`"$($paused2.thread_id)`",`"decision`":`"cancel`"}"
```

## Phase C5 — Streaming tool events

`POST /chat/stream` (and `/chat/resume/stream`) returns **SSE** so the UI can show tools as they run.

| Event | Meaning |
|-------|---------|
| `start` | `{ thread_id }` |
| `tool_start` | Tool name + args (chip appears) |
| `tool_end` | Result preview (chip completes) |
| `awaiting_confirmation` | HITL pause payload (same shape as `/chat`) |
| `final` | Completed turn + `answer` + `trust` |
| `error` | Failure detail |

```powershell
$token = (Invoke-RestMethod -Method POST -Uri http://localhost:8000/auth/login -ContentType "application/json" -Body '{"persona_id":"northstar"}').access_token

# Prefer curl.exe for raw SSE (PowerShell ConvertTo-Json will buffer)
curl.exe -N -X POST http://localhost:8000/chat/stream `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  -d "{\"message\":\"Can I cancel ORD-1001 without a fee?\"}"
```

Frontend (assignment §11): open `http://localhost:3000`, pick a persona, chat — **tool chips** appear live; confirm modal on write actions.

```powershell
cd apps/web
npm install
npm run dev
# API must be on :8000 (or set NEXT_PUBLIC_API_URL)
```
