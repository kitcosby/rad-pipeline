# Decision log

Newest first. Every entry names who decided, when, and what exactly was decided. Unresolved choices are recorded as OPEN with their owner.

## D-004 — WP2 and WP3 merged (executed 2026-11-12, under D-003)

The first two build packages were merged to `main` as merge commits:

- **PR #1 (WP2 — contracts and evidence store)** merged 2026-11-12;
  merge commit `c2add431`.
- **PR #2 (WP3 — orchestration core)** merged 2026-11-12;
  merge commit `7b64b5a8`.

Both packages were verified on two engines before merge (VM Python
3.12 and the Lampy distro Python 3.10, via Gwen's pipeline cross-runs:
WP2 44/44 on both, WP3 45/45 on both). GPT's evidence reviews of the
merged state follow through the queue (standing review lane, D-003).

Manual leftovers, recorded so they are not mistaken for done: the
repository currently has no tag tooling in the connector used for
these merges, so the `<component>-<YYYY-MM-DD>` version tags for the
two merge commits have NOT been created yet, and the merged branches
(`wp2-contracts-evidence`, `wp3-orchestration-core`) have NOT been
deleted. Both remain Kit-or-connector follow-ups.

## D-003 — Standing approval: verified work packages flow end-to-end (Kit, 2026-11-12 16:30 PT)

Kit's ruling, in substance verbatim: the hope is that the end of one
script triggers the next script, so that he does not need to keep
making these decisions; he would like to always allow it.

Recorded as a standing approval for the RAD pipeline:

- A work package that is **dual-engine-verified** (built per the
  implementation plan; test suite green on the VM engine and on the
  Lampy distro engine via the independent pipeline cross-run) flows
  **build → verify → branch → PR → merge-commit** without per-step
  decisions from Kit. Kit's recorded go for merges in this class is
  this entry.
- The intent is chaining: the end of one stage triggers the next,
  matching the pipeline's own cycle-close design (D-001). Operators
  (Muse, GPT) do not stop to re-ask inside the class.
- **Outside the class, Kit's explicit approval is still required:**
  production changes of any kind, destructive operations, service
  restarts, production data writes, semantic changes to requirements
  or CEGs, and anything not a dual-engine-verified work-package merge.
- GPT's post-merge evidence reviews are the review lane for this
  class: reviews happen, findings are filed, but they follow the
  merge rather than gating it. Merge-blocking findings are still
  surfaced to Kit as decisions (fix-first vs merge-as-is is moot
  post-merge; the follow-up correction becomes its own work package).

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
