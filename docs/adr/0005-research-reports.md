# 0005 — Research reports: metadata via API, both source and display

**Status**: accepted

ADR-0001 named 研报 as the primary source material for the hybrid generation
model. We now pin how 研报 are acquired, stored, and used.

## Decision

研报 are **cited objects**, not chain entities. They have their own simple
lifecycle, separate from the Generated/Canonical/Deprecated lifecycle of
entities.

### Acquisition

研报 metadata is fetched via the `a-stock-data` sources:

- `astock` (东方财富) — primary research report API.
- `tushare.report_rc` — secondary, when `TUSHARE_TOKEN` is set.
- `iwencai` (同花顺) — supplementary, for Q&A-style summaries.

**No PDF scraping in v1.** Brokerage PDFs are unreliable to parse, vary in
format, and carry ToS risk. The API metadata is enough signal for both
roles.

### Storage

`research_reports` table:

- `id`, `ticker` (which Company the report is about)
- `title`, `publish_date`, `rating` (e.g., 买入 / 增持 / 中性),
  `target_price`
- `broker`, `analyst` (optional)
- `summary` (1–2 paragraph abstract from the API)
- `source_url`, `source_api` (∈ {astock, tushare, iwencai})
- `fetched_at`, `status` (∈ {available, removed})

Linkage is **by ticker** for v1 — no separate `entity_citations` junction.
A Company's "Latest 研报" panel reads
`WHERE ticker = ? ORDER BY publish_date DESC LIMIT 5`. Provenance tracking
(which report supports which entity claim) is deferred to v2.

### Roles

1. **Display artifact.** "Latest 5 研报" panel on the A-share Company detail
   page.
2. **Source material for generation.** When generating or regenerating an
   entity (Company description, Sub-industry summary, Alternative edge),
   DeepSeek is passed the latest N report summaries as context.

### Lifecycle

研报 have `status ∈ {available, removed}`:

- `available` — shown on detail pages, eligible as LLM input.
- `removed` — broker took it down, or it was retracted. Hidden from views,
  retained for history.

研报 do NOT carry the `generated | canonical | deprecated` lifecycle. They
are facts about the world (a broker published this on this date), not
authored content.

## Considered options

- **Display only** (no LLM input). Gutted the hybrid model from ADR-0001.
  Rejected.
- **Full PDF scraping.** Heavy, brittle, ToS risk. v2 candidate at earliest.
  Rejected for v1.
- **Metadata via API, both roles** (accepted). Cheapest viable engine for
  the hybrid model.

## Consequences

- One new table (`research_reports`), one new TTL (`CACHE_TTL_REPORT` ≈ 1
  day, since 研报 publish daily but we don't need minute-freshness).
- The generation pipeline (ADR-0001) reads from `research_reports` as part
  of its context assembly.
- Companies with no recent 研报 (small caps, Reference Companies) fall back
  to LLM generation with no report context — output is marked
  lower-confidence in the UI.
