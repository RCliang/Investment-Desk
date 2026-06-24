# 0001 — Hybrid knowledge model: curated skeleton + LLM augmentation

**Status**: accepted

We are building an AI industry chain knowledge base shaped like
[aichainmap.com](https://aichainmap.com/) — browsable, structured,
cross-referenced — but cannot afford months of manual curation, and cannot
accept the hallucination and zero-browsability cost of generating everything
at view time via DeepSeek.

## Decision

Canonical entities (the structural set — Layers, Sub-industries, Companies,
plus cross-reference types resolved in later design questions) live in the
database with a `status` field taking one of three values:

- `generated` — DeepSeek draft produced from source material, not yet reviewed.
- `canonical` — human-approved, shown by default in the explorer.
- `deprecated` — superseded or removed, retained for history, hidden by default.

DeepSeek generates entity detail (descriptions, summaries, cross-references)
from source material — research reports (研报), financial filings, news — into
`generated` rows. A human review step promotes `generated` → `canonical`.
Views read only `canonical` by default.

Live market data (real-time quotes, financial indicators, fund flow) **never
passes through the LLM**. It is fetched directly from the `a-stock-data`
sources (akshare / astock / tushare) and TTL-cached in the existing
`data_cache` table.

## Considered options

- **Fully curated** (aichainmap.com today). Highest fidelity, highest editorial
  cost. Rejected as unsustainable for a solo project.
- **Fully dynamic** (v0 today: `POST /api/chain/analyze` → DeepSeek → JSON on
  every request). Zero browsability, hallucination risk, slow, expensive.
  Rejected — structurally incompatible with a knowledge graph.
- **Hybrid** (accepted). LLM as research engine, human as gatekeeper.
  Hallucinations are non-fatal because drafts require promotion.

## Consequences

- Every entity table carries `status`, `source` (citation of the source
  material used), and review metadata (`reviewed_by`, `reviewed_at`).
- A review/edit workflow is required. v0 of that workflow is direct DB edits
  or an admin endpoint; a UI comes later.
- Live market data and curated entity data live in separate tables with
  different freshness contracts.
- v0's `chain` router (`POST /api/chain/analyze`) is removed. The new chain
  explorer is read-driven: `GET` over canonical entities. Generation happens
  out-of-band during curation, not on the request path.
