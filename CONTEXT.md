# InvestLens v1 — AI Industry Chain Knowledge Base

A vertical knowledge base structuring the AI industry into layers,
sub-industries, and companies — modeled on
[aichainmap.com](https://aichainmap.com/). Replaces v0's generic "input any
industry → LLM emits JSON" workflow with a curated, browsable graph. See
[ADR-0001](./docs/adr/0001-hybrid-knowledge-model.md) for the knowledge model.

## Language

### Structural entities

**Node**:
Any entity in the AI chain — a Layer, Sub-industry, Company, or any
cross-reference type added later. Generic term used when referring to chain
elements without specifying type.
_Avoid_: Item, entry, element, thing.

**Layer**:
A horizontal slice of the AI chain. The seed set is fixed at five, in order:
能源 (Energy), 芯片 (Chips), AI基础设施 (AI Infrastructure),
AI基础模型 (Foundation Models), AI应用 (AI Applications). See
[ADR-0002](./docs/adr/0002-seed-layer-set.md). The set is closed; amendments
require an ADR.
_Avoid_: Tier, level, band, stage.

**Sub-industry**:
A node within a Layer that groups companies delivering similar products or
services (e.g., "GPU design" within the chips layer). The v1 seed (48
Sub-industries × ~339 unique companies) is adopted verbatim from
aichainmap.com's atlas; see
[ADR-0007](./docs/adr/0007-aichainmap-canonical-layers.md). iwencai and
East Money are backfill sources for market data, not classification
authorities.
_Avoid_: Category, segment, sector, vertical.

**Company**:
An operating business assigned to one or more Sub-industries across Layers.
A single Company may have multiple Listings (e.g., 中芯国际: 688981.SH +
0981.HK). See also Reference Company. When we need to refer to the listed
security, we say Listing or Ticker, not Company.
_Avoid_: Stock, ticker, issuer, name (when referring to the entity).

**Concept**:
A thematic tag that spans Layers and Sub-industries (e.g., 国产替代, 边缘AI,
AI眼镜). Concepts group Companies by investment theme rather than by
structural position. Seed Concepts mirror akshare's `stock_board_concept_*`
sectors.
_Avoid_: Theme, topic, label, tag.

**Reference Company**:
A non-A-share Company (e.g., NVIDIA, TSMC, OpenAI) included as comparison
context, not as an investable target. Same table as Company; distinguished by
`listing_market ∉ {SH, SZ, BJ}`. Has no live market data or financials — the
UI shows curated description plus cross-references to A-share alternatives.
_Avoid_: Foreign company, global peer, comparator.

### Relationships

**Cross-reference**:
Any relationship between two entities in the chain. The user-facing term for
"these two entities are connected." Implementation-wise, a row in one of the
junction tables.
_Avoid_: Edge, link, connection, relation.

**Alternative**:
An A-share Company that serves as an investable substitute for a Reference
Company (e.g., 海光信息 is an Alternative to NVIDIA). Stored in the
`company_alternatives` junction. The single most valuable cross-reference
type for an A-share investment tool.
_Avoid_: Peer, substitute, replacement, domestic version.

### Markets and listings

**Listing**:
A specific quoted security of a Company on a single exchange (e.g.,
688981.SH). Most Companies have exactly one Listing; some have multiple
(A+H, A+DR). For v1, Listings are stored as a value object on the Company
row.
_Avoid_: Ticker (when emphasizing the row), symbol, code.

**Ticker**:
The short code identifying a Listing on its exchange (e.g., "688981" for
中芯国际 on SH, "NVDA" for NVIDIA on NASDAQ). Used as the key in API calls to
akshare / astock / tushare. Informal synonym for Listing when the exchange is
implied.
_Avoid_: Code, symbol.

### Source material

**Research Report** (研报):
A sell-side analyst publication about a specific Company — title, publish
date, rating (e.g., 买入 / 增持 / 中性), target price, broker, summary.
Fetched via `astock` / `tushare.report_rc` / `iwencai`; never scraped from
PDF in v1. Stored in `research_reports` linked by ticker. A cited object,
not a chain entity — does not carry the Generated / Canonical / Deprecated
lifecycle.
_Avoid_: Report, analyst note, PDF, writeup.

### Data lifecycle

**Canonical**:
An entity whose content has been human-reviewed and is shown by default in the
explorer. Only Canonical nodes appear in public views.
_Avoid_: Approved, published, live, final.

**Generated**:
An entity whose content was produced by DeepSeek from source material (研报,
financials, news) and is awaiting review. Stored in the DB, hidden from
default views.
_Avoid_: Draft, pending, suggested, AI-generated.

**Deprecated**:
An entity that was once Canonical but has been superseded or removed. Retained
for history; hidden from default views.
_Avoid_: Archived, retired, deleted, old.
