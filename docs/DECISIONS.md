# Decision log

Newest first. Every entry names who decided, when, and what exactly was decided. Unresolved choices are recorded as OPEN with their owner.

## D-002 — WP1 placements approved (Kit, 2026-11-12 16:15 PT)

Kit approved both recommendations from the WP1 discovery
(`RECOMMENDATION.md`, discovery copy held by Muse):

1. **Canonical repository:** public `kitcosby/rad-pipeline` (this repo) holds
   the pipeline core. Runtime code does NOT live in the non-Git gpt-queue
   operations folder.
2. **Runner host:** on-demand inside the Lampy WSL distro — dedicated
   unprivileged user `radpipe` (uid 1001), workspace
   `/home/mcpgw/projects/rad-pipeline/` (setgid, group `mcpgw`, so the Lampy
   plugin can reach the scripts; subdirs `runs/`, `evidence/`, `work/`).
   No daemon, no Supervisor program, no schedule.

Implementation begins from this decision. The milestone Kit named for the
partnership: the build is "beyond needing Muse's shell commands" when the
WP2/WP3 artifacts are deployed into that workspace and GPT can invoke the
scripts through the Lampy plugin directly.

## D-001 — Design shape: structured pipe (Kit, 2026-11-12)

The pipeline is a structured pipe in the COBOL sense — declared inputs,
fixed stages, declared outputs — arranged as a Möbius cycle: a cycle's
outputs include the next cycle's intake package as a first-class output.
The point is structural, not linguistic; an OO implementation is fine.
Consequences: the scheduler (WP3) is a stage pipe first (parallelism inside
a stage or between provably independent stages), and cycle-close emits the
next intake.

## OPEN

- OPEN (owner: Kit): plugin `exec_run` connector-layer refusal seen during
  GPT's first queue pull ("link_id must identify an eligible linked
  account"; zero exec calls reached the gateway). Must be understood before
  GPT-driven execution is treated as trustworthy; tracked in the queue.
