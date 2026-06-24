# 0004 — v1 cross-reference model: structural + alternative_to

**Status**: accepted

ADR-0003 fixed the v1 entity set at four types (Layer, Sub-industry, Company,
Concept) plus Reference Company. We now pin the relationship model between
those entities.

## Decision

v1 has four relationship types, stored as three junction tables plus one FK:

1. **Layer → Sub-industry** — `sub_industries.layer_id` (FK, many-to-one).
2. **Sub-industry ↔ Company** — `company_sub_industries` junction
   (many-to-many). A Company can sit in Sub-industries across multiple
   Layers.
3. **Concept ↔ Company** — `company_concepts` junction (many-to-many).
4. **Company ↔ Reference Company** — `company_alternatives` junction
   (many-to-many). Each row says "A-share Company X is an Alternative to
   Reference Company Y." Powers the "A-share alternatives to NVIDIA" view.

All three junction tables carry the lifecycle columns from ADR-0001:
`status ∈ {generated, canonical, deprecated}`, `source`, `reviewed_by`,
`reviewed_at`. A DeepSeek-suggested edge starts as `generated` and is
promoted to `canonical` by human review.

## Out of scope for v1

- **General Company-to-Company typed edges** (supplier_of, customer_of,
  competitor_of, peer_of, derived_from). These are real features requiring
  per-type curation; adding the table before the curation exists would
  produce an empty schema. Revisit when at least one edge type has a
  concrete curation plan.

## Storage

- **SQLite is sufficient.** Scale estimate: ~884 Companies × ~5
  relationships average ≈ 4K junction rows. Well within SQLite's capacity.
- **No graph database.** v1 queries are all 1-hop (e.g., "Concepts of
  Company X", "Alternatives to Reference Company Y"). Path-finding across
  multi-hop supply chains is a v2+ concern; if it materializes, layer a
  graph index over the relational base rather than migrating the source of
  truth.

## Considered options

- **Structural only** (no company-to-company edges). Loses the A-share-
  Alternatives view, which is the single most valuable cross-reference for
  an A-share investment tool. Rejected.
- **Rich typed edges** (general `company_edges` table). Most expressive but
  most typed edges would be empty on day one. Rejected for v1.
- **Structural + alternative_to** (accepted). Unlocks the highest-value
  use case with minimal curation burden.

## Consequences

- Three junction tables, all sharing the same lifecycle schema.
- The "A-share Alternatives" view reads from `company_alternatives`; the
  Reference Company detail page shows inbound Alternatives, the A-share
  Company detail page shows outbound Alternatives.
- v2 can add a general `company_edges` table without disrupting v1
  relationships — the two coexist.
