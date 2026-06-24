# 0002 — Seed layer set: aichainmap.com's 5 layers

**Status**: accepted

ADR-0001 commits us to a curated knowledge graph. The graph needs a
structural backbone. aichainmap.com is the cited reference and uses a 5-layer
"cake" that is widely understood; we adopt it verbatim as the seed rather than
inventing a custom framework.

## Decision

The chain is structured into exactly **five Layers**, ordinal, not
user-editable:

| `layer_order` | Name (zh) | Name (en) | Scope |
| --- | --- | --- | --- |
| 1 | 能源 | Energy | Power generation, grid, cooling for AI workloads |
| 2 | 芯片 | Chips | GPU/ASIC design, foundry, packaging, memory, materials |
| 3 | AI基础设施 | AI Infrastructure | Compute cloud, data centers, data labeling, storage |
| 4 | AI基础模型 | Foundation Models | LLMs, multimodal, voice/vision models, model hubs |
| 5 | AI应用 | AI Applications | Productivity, vertical SaaS, agents, AI hardware |

Rules:

- **The Layer set is closed.** Layers are not user-defined. Only their
  *contents* (Sub-industries, Companies, cross-references) are editable.
- **A Sub-industry belongs to exactly one Layer.** No multi-layer
  sub-industries.
- **A Company may belong to Sub-industries in different Layers.** That is the
  source of most cross-references (handled in a later design question).
- **Amendments require an ADR.** If 研报 consistently surface a real need to
  split, merge, add, or remove a Layer, write ADR-NNNN to amend this set.
  Expected (not yet decided) candidates: splitting AI基础设施 into 数据 +
  算力/云; adding a 国产替代 cross-cutting axis.

## Considered options

- **Customize for A-share immediately.** Higher editorial burden, diverges
  from the reference, harder to defend before we have evidence from 研报.
  Rejected.
- **Lock permanently, no amendments.** Too rigid — real A-share research may
  surface genuine structural differences. Rejected.
- **Seed + amend via ADR** (accepted). Cheap defensible starting point,
  retains the right to evolve.

## Consequences

- The `layers` table (or enum) has exactly 5 rows; migrations to add/remove a
  Layer are ADR-gated.
- Layer order is stable across the UI; the explorer renders layers top-to-
  bottom in the order above.
- Sub-industry seed data needs to be authored per Layer — this is the first
  concrete curation task after the schema is in place.
