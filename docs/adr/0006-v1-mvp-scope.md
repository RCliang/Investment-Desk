# 0006 — v1 MVP scope: browsing + live data + 研报, manually curated seed

**Status**: accepted

ADRs 0001–0005 fixed the knowledge model, layer framework, entity set,
relationship model, and 研报 pipeline. We now define what "v1 ships" means.

## Decision

v1 ships the *product surface* — schema, read paths, frontend explorer, live
data integration, 研报 display — with **manually curated Canonical entities**.
The DeepSeek generation pipeline is deferred to v1.1.

### In scope for v1

**Schema** (new tables):

- `layers` (5 fixed rows per ADR-0002)
- `sub_industries`
- `companies`
- `concepts`
- `company_sub_industries` (junction)
- `company_concepts` (junction)
- `company_alternatives` (junction per ADR-0004)
- `research_reports` (per ADR-0005)

The v0 `chain_analyses` table is dropped.

**Seed data** (YAML fixtures in `backend/data/seed/`):

- 5 Layers (per ADR-0002)
- ~25 Sub-industries (5 per Layer as starting cut)
- ~50 A-share Companies, concentrated in Chips / Foundation Models /
  Applications (the layers that matter most for AI investing)
- ~8 Reference Companies: NVIDIA, TSMC, AMD, ASML, OpenAI, Google, MSFT, AWS
- ~20 Concepts (mirroring akshare concept sectors)

A `backend/scripts/seed.py` CLI loads the YAML idempotently (re-running it
updates rather than duplicates). Curated entities are inserted directly as
`canonical` status, bypassing the Generated step.

**Read paths**:

- `GET /api/chain/layers`
- `GET /api/chain/layers/{order}/sub-industries`
- `GET /api/chain/sub-industries/{slug}`
- `GET /api/chain/companies/{ticker}` (includes cross-refs)
- `GET /api/data/companies/{ticker}/quote`
- `GET /api/data/companies/{ticker}/financials`
- `GET /api/data/companies/{ticker}/fund-flow`
- `GET /api/data/companies/{ticker}/reports`

**Frontend**:

- ChainPage → Chain explorer (layer browser → sub-industry → company)
- CompanyDetailPage with 4 live panels + 研报 list + cross-refs
- Reference Company detail page (curated description + inbound Alternatives)
- PlanPage and ReportPage hidden from navigation

### Out of scope for v1 (deferred to v1.1+)

- DeepSeek generation pipeline (CLI to generate entity drafts from 研报)
- Review workflow UI (admin endpoint for promoting Generated → Canonical)
- General Company-to-Company typed edges (ADR-0004)
- Person, Event, Giant Chain entities (ADR-0003)
- Frontend editing UI (admin via CLI for now)
- Mini-program client (deferred indefinitely per user direction)

## Considered options

- **Browsing only** (no live data, no 研报). Ships fastest, proves nothing
  about data integration or the source-of-truth pipeline. Rejected.
- **Full v1 with generation pipeline**. ~30% more work, depends on LLM
  quality. Generation is cleanly separable from browsing — ship browsing
  first, generation as v1.1. Rejected for v1.0.
- **Browsing + live data + 研报, manual seed** (accepted). Exercises every
  layer of the stack without depending on LLM output quality.

## Consequences

- Schema migration is one-way: dropping `chain_analyses` removes v0 chain
  analysis history. Take a DB backup before running the migration.
- The v0 spec at
  `docs/superpowers/specs/2026-06-21-investment-desk-design.md` becomes
  historical; mark its header as superseded.
- A new v1 design doc should be written once grilling wraps, summarizing
  ADRs 0001–0006 and the read-path contracts.
- v1.1 (generation pipeline) does not require schema changes — only a new
  write-side script and an admin endpoint.
