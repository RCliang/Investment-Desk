# 0003 — v1 entity set: Layer, Sub-industry, Company, Concept

**Status**: accepted

ADR-0002 pinned the Layer set. We now pin which entity types populate the
graph for v1. aichainmap.com uses seven; we adopt four for v1 and defer the
rest to keep curation load honest.

## Decision

The v1 knowledge graph contains four entity types:

- **Layer** — fixed set of 5 (ADR-0002).
- **Sub-industry** — belongs to exactly one Layer.
- **Company** — an operating business; may sit in multiple Sub-industries
  across Layers; is a single entity even if multi-listed.
- **Concept** — a thematic tag spanning Layers and Sub-industries
  (e.g., 国产替代, 边缘AI).

Plus one Company sub-type:

- **Reference Company** — a non-A-share Company (e.g., NVIDIA, TSMC, OpenAI)
  included as comparison context. Same table, different rendering: no live
  market data, no financials (no data source for them), just curated
  description + cross-references to A-share alternatives. Distinguished by
  `listing_market ∉ {SH, SZ, BJ}`.

Deferred (out of v1, candidates for later):

- **Person** — not investment-relevant for a retail A-share tool.
- **Event** — partially covered by existing `astock` news feeds; a dedicated
  Event entity adds ongoing editorial load without clear payoff.
- **Giant Chain (巨头链)** — needs ~13 dense curated cross-layer narratives to
  be worth shipping; deserves its own dedicated build, not a half-baked
  inclusion.

## Rules

- **Company is a single entity even if multi-listed.** 中芯国际's 688981.SH
  (A-share) and 0981.HK (Hong Kong) are two listings of one Company. v1
  stores ticker + market as a value object on the Company row; if
  multi-listing proves common, split to a separate `listings` table via
  migration.
- **Concept seed mirrors akshare's `stock_board_concept_*` sectors**, not
  independently curated. Custom Concepts can be added later (no ADR required —
  Concepts are user-editable content, not schema).
- **Reference Company has no live data jobs.** The market-data fetching
  services (`akshare_service`, `tushare_service`, `astock_service`) are never
  called against its ticker; the UI hides financial panels for it.

## Considered options

- **Lean (Layer, Sub-industry, Company).** Loses thematic screens, which are
  how A-share concept rotation actually works. Rejected.
- **Full parity (add Person, Event, Giant Chain).** 2–3× editorial load, and
  Person/Event are not core to an investment tool. Rejected for v1.
- **Lean + Concept** (accepted). Cheap (mirrors akshare), high value (enables
  thematic screens), keeps scope honest.

## Consequences

- Four entity tables, or one `nodes` table with a `type` discriminator — the
  shape is decided in the cross-reference design question.
- The Company detail page branches on `listing_market`: A-share → full live
  data; otherwise → curated only.
- A migration path to add Person / Event / Giant Chain later does not disrupt
  the four v1 entities (each would be a new table or a new `type` value).
