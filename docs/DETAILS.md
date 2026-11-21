<img src="docs/logo.png" alt="OxisTrack logo" width="96">

# OxisTrack

**Know what changed. Know what's missing. Know what to do next.**

OxisTrack is a project intelligence and verification platform. Upload the documents that describe a
project - proposals, meeting notes, specs, spreadsheets - and it extracts the facts they state, finds
where they contradict each other, checks your work against the requirements, and shows what a change
would ripple into.

Built for **Teens Hack Houston 2026** (technical track). Theme: *A More Efficient Way to Live.*
Nobody should spend an evening re-reading four documents to work out which deadline is the real one.

## How it works

One upload runs the whole pipeline. Nothing in it needs a click.

```
Uploaded documents            PDF · DOCX · XLSX · CSV · TXT · Markdown
        ↓
Document processing           extract facts, requirements and evidence
        ↓
Conflict engine  |  Verification engine
find disagreements  |  check requirements against the deliverable
        ↓
Knowledge graph               connect documents, facts, requirements and tasks
        ↓
Action Center                 impact reports and recommended next steps
```

**Autopilot** (on by default, switchable per project in Settings) makes the routine decisions:

- It picks the authoritative source when documents disagree. The choice is scored from the evidence: a
  source that calls its value an update, the most recently dated document, and agreement between
  documents. The reasoning and confidence are stored with the decision.
- It traces what each decision touches and files one impact report per decision.
- It approves the next steps it recommends, so they land in the Action Center as active tasks.

**Two AI models** (optional, set in `backend/.env`):

- The **AI analyst** (`LLM_MODEL`) reads documents, adds facts the rules miss, and gives its own opinion on
  each contradiction.
- The **AI reviewer** (`REVIEWER_MODEL`) is a second, independent model, ideally from a different vendor. It
  checks every source choice, breaks ties, and re-reads requirement checks that came back unclear.
- A decision needs two of three voices to agree: the evidence rules, the analyst and the reviewer. A
  requirement check is settled only when both models agree and each quotes a passage that is really in the
  deliverable. Anything else goes to a person.

The shared AI settings, including the OpenRouter key, are committed in `backend/.env.shared` so a fresh clone
runs with both models. **Keep this repository private while that file is in it**, and rotate the key before
making the repo public. One OpenRouter key reaches both models, for example `anthropic/claude-haiku-5.5` as analyst and
`openai/gpt-4.1-mini` as reviewer. Without any key the app runs on the rule-based engine alone.

Every Autopilot decision is in the evidence timeline, and any of them can be overruled with one click.
When the sources are evenly matched, Autopilot does not guess and leaves that one to a person. With
Autopilot off, you choose each source and approve each task yourself.

![Contradictions shown side by side with their sources](docs/screenshots/contradictions.png)

| | |
|---|---|
| ![Overview](docs/screenshots/overview.png) | ![Ripple impact report](docs/screenshots/ripple-impact.png) |
| ![Knowledge graph](docs/screenshots/knowledge-graph.png) | ![Requirement verification](docs/screenshots/requirements.png) |

## What it does

| Area | What works |
|---|---|
| **Document intelligence** | Multi-file upload (PDF, DOCX, TXT, CSV, XLSX, Markdown), parsing, versioning, and fact extraction (deadlines, dates, requirements, decisions, goals, entities, budgets, quantities, specs, constraints, dependencies). Every fact stores its source document, location, confidence and timestamp. |
| **Contradiction detection** | Facts about the same subject are compared across documents. Conflicts are classified (deadline, budget, numerical, requirement, specification, inconsistent statement) and shown side by side with their evidence. Autopilot settles them from the evidence and records why; you can overrule any decision. |
| **Requirement compiler** | Requirements are extracted from documents during processing, and pasted instructions can be compiled too. Each becomes a separate requirement with an ID, category, priority, source and verification method. |
| **Verification** | Runs as soon as a deliverable is uploaded. Checks it against each requirement: deterministic keyword evidence (with detection of "not implemented"-style statements), numeric comparison, file-name checks, optional AI semantic review, and manual review. Each result records what was checked, the evidence, and why it passed, failed or needs review. |
| **Knowledge graph** | Interactive React Flow graph of documents, facts, topics, requirements, contradictions, decisions, tasks and deliverables, generated from stored records. Zoom, pan, drag, search, filter, select to highlight neighbours. |
| **Ripple impact** | "What if this changes?" - traverses the graph from a requirement or fact and reports directly and indirectly affected items, the reason for each, and a recommended action. A what-if you type changes nothing until you approve it. |
| **Action Center** | Impact reports and recommended next steps: failed checks, outdated documents, items needing review, near deadlines. Autopilot approves them; with Autopilot off, you do. |
| **Evidence timeline** | An audit trail that separates source statements, unresolved disagreements, confirmed changes and superseded sources. |
| **Search and ask** | Project-wide search (⌘K), plus a secondary assistant that answers only from extracted facts and always lists its sources and uncertainty. |
| **Easter egg** | There is a capybara somewhere in the knowledge graph. |

## Architecture

```
frontend/   Next.js 15 (App Router) · TypeScript · Tailwind · Radix (shadcn-style components)
            React Flow · Recharts · SWR · Phosphor Icons · sonner
            Plus Jakarta Sans (headings) · Geist (body)
backend/    FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · MySQL (PyMySQL)
            PyMuPDF · python-docx · openpyxl · JWT auth (bcrypt)
```

```
backend/
  app/
    main.py            FastAPI app, CORS, error handlers
    config.py          Settings from environment variables
    models.py          20 relational tables (users … activity_logs)
    schemas.py         Pydantic request/response models
    security.py        Password hashing, JWT, rate limiter
    deps.py            Auth + project-level access control
    routers/           auth, projects, documents, analysis (thin HTTP layer)
    services/
      parsing.py       File → citable text segments
      rules.py         Deterministic extraction + requirement compiler
      ai.py            Provider abstraction (rules engine / OpenAI-compatible LLM)
      pipeline.py      Upload storage, analysis pipeline, versions
      contradictions.py  Detection and resolution
      requirements.py  Compile from text or documents
      verification.py  Evidence-first requirement checks
      graph.py         Knowledge graph builder
      impact.py        Ripple impact analysis + apply
      autopilot.py     Source selection, ripple follow-ups, task approval
      tasks.py         Recommended next steps
      dashboard.py     Overview metrics and health score
      search.py        Search + evidence-citing answers
      demo.py          Sample project generator
  alembic/             Database migrations
  tests/               19 tests: engine unit tests + end-to-end API workflow
frontend/
  src/app/             login, (app)/overview, documents, documents/[id], verification, graph, actions, settings
  src/components/      app shell, panels, knowledge graph, timeline, ui/ primitives
  src/lib/             API client, session/project context, types
docker-compose.yml     Local MySQL
```

### About the AI layer

`AI_PROVIDER=auto` (the default) uses an LLM when `LLM_API_KEY` is set and the built-in **rule-based
engine** otherwise. The app is fully functional without a key - the Settings page shows which engine is
active.

When an LLM is configured (any OpenAI-compatible chat-completions API - set `LLM_BASE_URL`, `LLM_API_KEY`,
`LLM_MODEL`), it assists fact extraction, requirement compilation, semantic checks and the assistant. Its
output is validated against Pydantic schemas and never trusted blindly: a fact whose quote is not found
verbatim in the source segment is discarded, typed values are re-parsed deterministically, an AI "pass" is
accepted only when its quoted evidence exists in the deliverable, and any provider failure falls back to
the rules engine. Document text is passed as delimited, untrusted data.

## Run it locally

Requirements: Python 3.11+, Node 20+, MySQL 8 (or Docker).

### 1. Database

```bash
docker compose up -d          # starts MySQL 8 with database/user/password "oxistrack"
```

Or with an existing MySQL server:

```sql
CREATE DATABASE oxistrack CHARACTER SET utf8mb4;
CREATE USER 'oxistrack'@'%' IDENTIFIED BY 'oxistrack';
GRANT ALL ON oxistrack.* TO 'oxistrack'@'%';
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set SECRET_KEY
alembic upgrade head          # creates the schema
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs · Health: http://localhost:8000/health

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                   # http://localhost:3000
```

### Environment variables

**backend/.env**

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://oxistrack:oxistrack@127.0.0.1:3306/oxistrack?charset=utf8mb4` | MySQL connection |
| `SECRET_KEY` | *(must set)* | JWT signing key |
| `ACCESS_TOKEN_MINUTES` | `1440` | Session length |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed frontend origins |
| `UPLOAD_DIR` | `./storage` | Where uploaded files are stored |
| `MAX_UPLOAD_MB` | `15` | Per-file size limit |
| `AI_PROVIDER` | `auto` | `auto`, `heuristic` or `openai_compatible` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI URL / empty / `gpt-4o-mini` | AI analyst (any OpenAI-compatible API) |
| `REVIEWER_BASE_URL` / `REVIEWER_API_KEY` / `REVIEWER_MODEL` | same as analyst / same / empty | AI reviewer; off until a model is set |
| `ENVIRONMENT` | `development` | `production` refuses to start with a default secret |

**frontend/.env.local**

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL |

### Tests and checks

```bash
cd backend && pytest                                   # 19 tests (uses in-memory SQLite by default)
DATABASE_URL=mysql+pymysql://…/oxistrack_test pytest   # same suite against MySQL
cd frontend && npm run typecheck && npm run build
```

## Demo

On the sign-in page choose **Explore the sample project**. It creates a guest workspace and loads
*Mobile App Development Project* with three sample documents (DOCX, Markdown, PDF) that intentionally
disagree. They are generated and then sent through the same upload → parse → extract → detect pipeline as
any upload; no result is precomputed. Sample data is labelled as such throughout.

A good five-minute path (the Overview page shows it as a checklist):

1. **Sign in page** - click *Explore the sample project*. The three documents are processed on the spot.
2. **Verification → Contradictions** - the deadline was stated three ways (Dec 20 / 22 / 18), user roles two
   ways, the budget two ways. Each is already settled by Autopilot with its reasoning. Click *Overrule* on one.
3. **Verification → Requirements** - six requirements were extracted. Click *Use the sample deliverable*;
   it is verified on arrival. Notifications and the QA test plan fail; user roles fails (expected 5, found 3).
4. **Knowledge Graph** - select *User roles* to see what it touches. Find the capybara.
5. **Action Center** - active tasks, each with its reason. Open *Impact reports* to see what each decision
   touched, then run a what-if (change user roles to 7) and approve it.
6. **Overview → Evidence timeline** - the full audit trail, including every Autopilot decision.

**Reset:** Settings → *Reset sample project* (or `POST /demo/reset`). To try the pipeline by hand, create an
empty project; the Documents page offers the sample files as downloads to upload yourself.

## Security notes

- Uploads: extension allow-list, content sniffing, size limit, server-generated storage names (no
  client-controlled paths), files never executed.
- Auth: bcrypt password hashes, JWT bearer tokens, rate-limited auth and upload endpoints.
- Access control: every project-scoped route checks membership; non-members get 404. Viewer role is read-only.
- Secrets only via environment variables; errors returned to clients never include internals.
- Document content cannot change application behaviour: it is treated as data in both the rules engine and
  LLM prompts.

## Live app

**https://frontend-production-8cfd270e.up.railway.app**

Deployed on Railway as three services in one project: `frontend` (Next.js), `backend` (FastAPI, API at
https://backend-production-ff5cd2c9.up.railway.app) and `mysql` (MySQL 8 with a persistent volume). Code is
uploaded with `railway up` from `backend/` and `frontend/`; `.railwayignore` in each keeps local files out.
Uploaded documents are stored on the backend's disk and are cleared when the backend is redeployed.

## Install it as an app

OxisTrack is an installable web app. Once it is deployed (or running locally), open it in Chrome or Edge and
use the **Install app** button in the sidebar or on the sign-in page. On Windows and macOS it gets a desktop
icon, a Start menu or Launchpad entry, and its own window without browser bars. On a phone, use Share → Add to
Home Screen (iPhone) or the browser menu → Install app (Android). Settings → Install the app has the same
steps. The installed app still needs the server for data and AI, so it does not work offline.

## Deployment

- **Frontend:** Vercel (root `frontend/`, set `NEXT_PUBLIC_API_URL`).
- **Backend:** any Python host (Render, Railway, Fly.io): `pip install -r requirements.txt`,
  `alembic upgrade head`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `ENVIRONMENT=production`,
  `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, and mount persistent storage at `UPLOAD_DIR`.
- **Database:** any MySQL 8-compatible service.

## Known limitations

- Autopilot's choice of source is an evidence score (marked as an update, newest date, agreement between
  documents), not a guarantee. A newer document can be wrong, which is why every decision shows its reasoning
  and can be overruled.
- Without an LLM key, extraction is rule-based: it handles `Key: value` lines and clearly worded sentences
  ("must include…", "requires three…", "deadline is…") well, and will miss facts phrased loosely or spread
  across sentences. With an LLM key the analyst adds what the rules miss.
- Subjects are matched by normalised wording ("Project deadline" = "Updated project deadline"); two
  documents that name the same thing very differently will not be compared.
- Verification reads deliverable *documents*. It does not execute code or run test suites; such
  requirements should use manual review.
- Scanned PDFs need OCR, which is not included.
- Analysis runs in FastAPI background tasks (no external queue); the rate limiter is in-memory, per process.
- Search is keyword-based with light stemming, not embedding-based.
- Uploaded files are stored on local disk.
