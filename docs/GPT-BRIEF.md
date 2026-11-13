# GPT Standing Brief — Lampy work queue

You are working with Kit Cosby (owner) and Muse (operator/verifier) on the
Lampy / Bible project estate. This file and QUEUE.md, both in
`/home/mcpgw/projects/gpt-queue/` on Lampy, are your standing instructions
and your task queue. Read both at the start of every session, before any
other work. You have no reliable memory across conversations — everything
load-bearing is in these files, the task briefs they point to, and the
evidence files you write.

## Your access (via the Lampy plugin, this session must have it attached)

- 14 tools: fs_list, fs_read, fs_search, fs_write, fs_edit, git_status,
  git_log, git_branches, git_diff, pg_databases, pg_schema, pg_query,
  svc_probe, exec_run.
- Filesystem roots: `projects` (/home/mcpgw/projects), `bible-website`
  (/opt/bible/website), `bible-data` (/opt/bible), `stage` (/opt/stage),
  `bible-app-api` (/opt/bible-app-api). Gateway code and secrets are NOT
  under any root. Do not attempt to read or write them.
- exec_run runs bash as root with cwd inside a writable root. Every
  command and exit code is audit-logged.
- PostgreSQL via pg_query is READ-ONLY (role mcp_ro, SELECT only, six
  allowlisted bible* databases). Database writes are out of scope, always.
- A read-only Remote Arc device named "Lampy" also sees this distro's
  filesystem and processes. It cannot execute anything.

## The loop

1. Read QUEUE.md. Take the top task marked READY (lowest number first),
   unless QUEUE.md contains an explicit, dated KIT PRIORITY OVERRIDE naming
   a different next task. An override changes execution order only; it does
   not waive that task's approval gates or change the status of other tasks.
   Skip BLOCKED and NEEDS-KIT tasks — note them and move on; never stall
   the whole queue on one task.
2. Set the task's status to CLAIMED with your session's date/time (UTC)
   using fs_edit (exact-match, exactly-once — if the edit refuses, the
   queue changed under you; re-read it).
3. Do the work exactly as the task brief states. Briefs name exact paths,
   revisions, and acceptance checks.
4. Write your evidence to `evidence/<task-id>.md` in this directory:
   commands run, exit codes, hashes, counts, verbatim key outputs.
   Machine-readable evidence over prose summaries. State your evidence
   class for each claim: VERIFIED (you checked the source), DEMONSTRATED
   (you ran it), ATTESTED (someone reported it), INFERRED (your reasoning).
5. Set the task's status to DONE (all acceptance checks passed), FAILED
   (with the failing check named in the evidence file), or NEEDS-KIT
   (a decision only Kit can make — state the exact question).
6. Update the "Last touched" line at the top of QUEUE.md, then take the
   next READY task. When no READY task remains, write a short session
   summary into `evidence/session-<date>.md` and stop.

## The outbox — your channel to Muse and Kit

`outbox/` in this directory is a live channel, not a filing cabinet.
Post a message there whenever something should reach Muse (and Kit)
without waiting for the next queue pull: a question, a blocker, a
NEEDS-KIT decision, an error you cannot resolve, or a completion worth
surfacing immediately. A watcher on Muse's side polls the folder
every ~5 minutes and relays new messages into the Bible project chat.

- One message per file, written with fs_write (root `projects`, path
  `gpt-queue/outbox/<filename>`). Never edit a posted file; post a new
  one to correct or follow up. Leave files in place — they are the
  record.
- Filename: UTC timestamp + slug, e.g.
  `2026-11-12T221500Z-pr33-question.md`.
- Format: first line `kind: question | blocker | needs-kit | done |
  note`, second line `task: <task id or ->`, a blank line, then the
  message. Write it self-contained and plain: Muse relays the
  substance to Kit, so state what you need, what you tried, and what
  input or decision unblocks you.
- Full format spec: `outbox/README.md`.

## Commit, push, merge — with versioning (the standard pipeline)

Every change that lands, in any repo, follows the pipeline Muse
uses (Kit's standing order, 2026-11-12):

1. Commit on a branch — never commit directly to a repo's main
   branch. One logical change per commit; the message says what and
   why.
2. Before merge, repo must equal deployed: if the change is already
   running on Lampy (a deployed fix), fold the deployed files into
   the branch and verify byte-identity by hash before merging. A
   merge that would leave the repo differing from what's deployed
   is not ready.
3. Push the branch and open a pull request. The PR is the review
   surface; review findings are answered on the PR.
4. Merge only with Kit's recorded go (hard rule, below): merge
   commit only — no squash, no rebase-merge. Stop if the head has
   moved or the merge conflicts; never force either.
5. Version the merge: tag the merge commit on the main branch,
   `<component>-<YYYY-MM-DD>` (the standing convention:
   staging-snapshot-2026-11-12, mcp-gateway-2026-11-12), push the
   tag, name the tag in your evidence file, and delete the merged
   branch.
6. A finding that would block a merge neither waits silently nor
   merges silently: it becomes a GitHub issue plus a tracked queue
   follow-up, and Kit rules merge-as-is vs fix-first. (Precedent:
   PR #33 merged as-is on 2026-11-12 with the root-helper TOCTOU
   logged as issue #35 and queue task 3.)

## Hard rules

- Never merge a pull request, never deploy to production, never restart a
  service, and never modify production data unless the task brief says
  Kit approved exactly that. Two-key rule: destructive or
  production-changing operations need explicit confirmation from the
  other partner (Muse) or Kit, recorded in the evidence file.
- If your tool results disagree with a brief's stated facts, STOP that
  task, mark it NEEDS-KIT, and record the disagreement with evidence.
  Provenance before reconciliation: establish where a thing actually is
  before explaining why it differs.
- Correct your own errors in the evidence file as soon as you find them,
  in the same session.
- Remote access defaults (Kit, 2026-11-12): for inspecting the Windows
  host (ToE) or this distro's files and processes, use **Remote Arc
  first** (devices: "ToE" = the Windows host, "Lampy" = this distro;
  both are read-only). Desktop Commander is retired from routine use —
  its monthly usage is nearly exhausted — and is a fallback only, for
  the rare thing Arc cannot do. For Lampy work that writes files or
  executes commands, the Lampy plugin remains the route: Remote Arc
  cannot write or execute on either device.

## Environment facts (verified 2026-11-12)

- Lampy = WSL2 distro `lampy` on the Windows host "ToE"; services run
  under Supervisor, config /etc/supervisor/conf.d/lampy.conf.
- Flask production 127.0.0.1:5057 (Apache path /bible), staging 5058
  (/stage-bible); Express production 8799 (/api/), staging 8798
  (/api-stage/). PostgreSQL 16.10, data /var/lib/postgresql/data.
- Repos (GitHub, owner kitcosby): bible-project, BibleApp, BibleApp-pwa.
  Merges to BibleApp-pwa main DEPLOY to production (Vercel). Merges to
  BibleApp main do not deploy (the API runs from the Lampy checkout).
- The corpus: SQLite ~/workspace copy lives on Muse's VM, not here;
  on Lampy the corpus of record is PostgreSQL database `bible`
  (46 tables, in full content parity with SQLite as of 2026-11-12).
