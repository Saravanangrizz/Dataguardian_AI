# DataGuardian AI

**Autonomous AI Data Reliability & Governance Engineer, built on DataHub.**

Submission for [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).

DataGuardian AI reads an organization's metadata graph through DataHub, reasons
about reliability and governance risk with grounded evidence (not vibes), explains
*why* something broke by walking the lineage chain, and — critically — writes its
recommendations back into DataHub instead of just reporting them into a dashboard
no one reads.

## Why this isn't "another metadata browser"

Every finding below is produced by the same loop:

```
observe (real metadata/lineage signal)
   -> reason (rule-based evidence + optional LLM narrative)
   -> explain (plain-language, cites the evidence)
   -> act (writes a fix back into DataHub: owner, description, or tags)
```

The write-back step is the part most agent demos skip. DataGuardian AI doesn't
just say "this dataset needs an owner" — it drafts the owner assignment and
pushes it into DataHub's catalog via the same operations DataHub's own MCP
server exposes (`add_owner`, `update_description`, `add_tags`).

### Agents collaborate, they don't just run in parallel

`GET /api/investigate/{urn}` runs a single pipeline where each stage only
sees what the *previous* stage already decided — no stage re-derives facts
another stage already established:

```
Reliability Engineer        -> staleness + upstream pipeline health, with evidence
        |
Lineage Investigator        -> resolves raw urns into named dashboards/pipelines,
        |                       flags any dependency that doesn't resolve
Governance Officer          -> ownership / doc / PII gaps on this asset
        |
Business Impact Advisor     -> translates stages 1-3 into stakeholder language,
        |                       naming the actual downstream dashboard
Executive Summary           -> compresses stages 1-4 into a 3-4 sentence brief
```

The same call also returns an **incident timeline** (chronological events —
last modified, upstream failure, investigation completed) and a
**remediation plan**: a list of concrete proposed writes (assign owner, add
description, apply a tag), each with the exact value that would be written.
Nothing is written until the user reviews the plan and approves it via
`POST /api/actions/apply-batch` — see `InvestigationBoard.tsx` for the
review-then-approve UI. This mirrors how a human governance officer would
actually want to operate: propose, review, then act — never silently mutate
the catalog.

## Architecture

```
React + TypeScript + Tailwind  (frontend)
        │  /api
        ▼
FastAPI backend
   ├── DataHubClient        (mock in-memory client, or live client via the acryl-datahub SDK)
   ├── AI provider           (heuristic fallback, Anthropic, OpenAI, or Gemini)
   ├── agents/
   │     ├── reliability.py            (staleness + pipeline health, standalone findings feed)
   │     ├── governance.py             (ownership / docs / PII, standalone findings feed)
   │     ├── lineage_investigator.py   (resolves urns -> named, typed entities)
   │     ├── business_impact.py        (stage 4 of the pipeline)
   │     ├── executive_summary.py      (stage 5 of the pipeline)
   │     ├── pipeline.py               (orchestrator: chains all 5 stages for /investigate)
   │     ├── root_cause.py             (walks a single upstream chain for the case-board view)
   │     └── nlq.py                    (natural language query over the catalog)
        │
        ▼
   DataHub metadata graph (mock data out of the box, live GMS/MCP when configured)
```

`app/datahub_client.py` is the one seam in the codebase: swap `DATAHUB_MODE` from
`mock` to `live` and point `DATAHUB_GMS_URL`/`DATAHUB_TOKEN` at a real DataHub
instance, and every agent above keeps working unchanged.

Two ways to consume the agents from the frontend:
- `GET /api/findings` — reliability + governance findings across the whole
  catalog, for the dashboard-level ledger view
- `GET /api/investigate/{urn}` — the full 5-stage collaboration pipeline for
  one specific asset, for the deep-dive "run full investigation" view

## Running it (zero setup, demo mode)

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8010

# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open the printed Vite URL. With no `.env` at all, the app runs against
built-in sample metadata (`app/sample_data.py`) and a deterministic
rule-based "heuristic" reasoner — no API keys required to see real findings,
a real write-back loop, and a real root-cause trace.

## Turning on real LLM reasoning

Copy `backend/.env.example` to `backend/.env`, set:

```
AI_PROVIDER=anthropic       # or openai / gemini
ANTHROPIC_API_KEY=sk-...
```

and install the matching SDK (`pip install anthropic`, `openai`, or
`google-generativeai`). The agent code does not change — only
`app/ai_provider.py`'s factory function picks a different backend.

## Pointing at a real DataHub instance

`LiveDataHubClient` in `app/datahub_client.py` uses the official
`acryl-datahub` Python SDK (`DataHubGraph`) rather than hand-rolled
GraphQL — every method shape (`get_ownership`, `get_tags`, `get_aspect`,
`emit_mcp`, the schema classes like `OwnershipClass`/`GlobalTagsClass`)
was copied from `inspect.signature()` on the installed package, not
guessed from docs that can drift between DataHub versions. To connect it:

1. **Find your GMS port.** The DataHub UI you browse to (e.g.
   `http://localhost:9002`) is the *frontend* — the SDK talks to a
   separate GMS service, commonly `http://localhost:8080` in a standard
   `datahub-quickstart` setup. `DATAHUB_GMS_URL` must point at GMS, not
   the UI port.
2. **Generate a token.** In the DataHub UI: Settings → Access Tokens →
   Generate New Token.
3. **Sanity-check the connection before touching the app:**
   ```bash
   cd backend
   DATAHUB_GMS_URL=http://localhost:8080 DATAHUB_TOKEN=<your-token> \
     python3 scripts/check_live_connection.py
   ```
   This runs one read-only search query and prints the datasets it can
   see. Fix any connection/auth error here first — it's much faster to
   debug than through the full app. (This script is intentionally raw
   `httpx`, not the SDK — it isolates "is the network path even open"
   from "is the SDK happy," which are two different failure modes.)
4. Set `DATAHUB_MODE=live`, `DATAHUB_GMS_URL`, `DATAHUB_TOKEN` in
   `backend/.env`, restart `uvicorn`, and the dashboard now reads your
   real catalog.
5. Only set `DATAHUB_WRITE_ENABLED=true` after step 3 succeeds. Every
   write reads the existing aspect first and merges into it (see the
   comments in `write_owner`/`write_tags`) so approving a remediation
   doesn't silently wipe out owners/tags a human already set in the UI.

**Two things worth knowing before you rely on this against your live instance:**

- **It fails fast, not silently.** Two real bugs surfaced while wiring
  this up, both fixed: the SDK's default timeout/retry settings
  (`timeout_sec=None`, `retry_max_times=None`) retry indefinitely on a
  connection failure — confirmed by testing against a dead port, which
  hung rather than erroring — so this client sets explicit `timeout_sec=10,
  retry_max_times=1`. Separately, the SDK's `list_all_entity_urns`
  swallows connection/auth errors internally and returns `None` rather
  than raising, which would otherwise present "0 datasets" as a clean,
  empty catalog instead of a broken connection — this client checks for
  that `None` and raises explicitly instead.
- **What you get for free vs. what needs mapping:** ownership,
  documentation, and tag/PII-tag gaps are read directly from real
  DataHub fields, so those findings are accurate against your instance
  immediately. Staleness/freshness and pipeline-health findings depend
  on concepts DataHub has no single native field for
  (`expected_freshness_hours`, `criticality`, pipeline `last_run_status`)
  — `_map_dataset_sync` in `datahub_client.py` currently defaults these
  rather than guessing wrong. Wire them to a DataHub Structured Property
  or your ingestion pipeline's own signals for real values.

## What's in `examples/`

`sample_findings.json`, `sample_root_cause.json`, and
`sample_investigation.json` are real output from this codebase (not
hand-written) — running the agents, root-cause tracer, and full
collaboration pipeline against the bundled mock metadata. Judges can
read these without running anything to see the shape and quality of
what the agents produce.

## Honesty about the demo data

Out of the box, `DATAHUB_MODE=mock` serves realistic-but-invented metadata so
the whole loop is runnable in under a minute with no DataHub instance to
stand up. The "failure prediction" confidence scores are rule-derived ratios
(time-overdue / expected-freshness), not a trained model — this is stated
explicitly in each finding's `reasoning_source` field rather than dressed up
as machine learning it isn't.

## Roadmap (post-hackathon, not in this MVP)

- Blast-radius visualization across the full lineage graph (today's case
  board shows a single upstream chain, not the full multi-hop radius)
- What-if simulator ("what breaks if I delete this dataset")
- Slack/Jira write-outs for remediation actions
- Multi-provider side-by-side comparison in the UI (today it's one provider
  per deployment, chosen via env var)
- Persisting findings/audit log to Postgres instead of in-process memory
- A real (trained) reliability model — today's "prediction" is a rule-based
  ratio, stated honestly rather than dressed up as ML (see below)

These were cut deliberately to keep the MVP's core loop — read → reason
(as a collaborating chain, not isolated agents) → explain → review → write
back — solid and fully working end-to-end, rather than spreading effort
across twenty partially-working features.

## License

Apache 2.0 — see [LICENSE](./LICENSE).
