# rad-pipeline

An architecture-led rapid-application-development (RAD) pipeline: a **structured stage pipe** for evidence-first task orchestration. Declared inputs enter a cycle, pass through fixed stages (intake, contracts, evidence, scheduling, adapter work, reconciliation, acceptance), and produce declared outputs — including, at cycle close, the *next* cycle's intake package. Records in one end, through fixed declared stages, out the other.

Design authority and work packages live in [`docs/`](docs/):

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system shape and the MVP acceptance matrix
- [`docs/CONTRACTS.md`](docs/CONTRACTS.md) — versioned contracts between stages and adapters
- [`docs/STATE-MACHINE.md`](docs/STATE-MACHINE.md) — run/task states and transition guards
- [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md) — work packages WP0–WP7 and the critical path
- [`docs/INTEGRATION-MAP.md`](docs/INTEGRATION-MAP.md) — how existing assets (queue, gateway, CEG, adapters) connect
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — the decision log (approvals, placements, unresolved choices)
- [`schemas/`](schemas/) — versioned JSON schemas (finding record first)

## The team

- **Kit Cosby** — owner; holds authority and approvals (merges, production, destructive operations).
- **ChatGPT (GPT)** — independent architecture, testing, and evidence-review partner; works through the Lampy plugin and the project queue.
- **Muse** — builds, operates, verifies from source, and coordinates.
- **Gwen** — assists inside her trust boundary; her outputs are unverified leads, never evidence.

## Working rules (from the implementation plan)

- One branch per coherent work package; pull-request review before merge. No direct commits to `main` after seeding.
- No merge, production deployment, service restart, or production data write without Kit's recorded approval.
- Tests and evidence accompany each package; docs change in the same delivery as behavior.
- Evidence is append-only, content-hashed, and written before interpretation.

## Runtime placement

The non-production runner lives in the Lampy WSL distro on the Windows host "ToE": dedicated unprivileged user `radpipe`, workspace `/home/mcpgw/projects/rad-pipeline/` (under the MCP gateway's projects root so the Lampy plugin can reach it). On-demand only — no daemon, no scheduler entry. Pilot project: **BibleApp QA**, non-production first. CEG generation stays gated until the standing paradigm-cleanup gate is DONE.

## Status

- WP0 architecture: complete (spec batch).
- WP1 placement: **decided 2026-11-12** — this repository; runner as above. See `docs/DECISIONS.md`.
- WP2 contracts & evidence store: next.
