# RAD Pipeline — Existing Infrastructure and Queue Integration Map

Date: 2026-11-12  
Status: inventory baseline v0.1  
Evidence companion: ../evidence/RAD-PIPELINE-FOUNDATION.md

## 1. Existing infrastructure map

| Existing component | Current role / verified state | RAD pipeline responsibility | Integration approach |
|---|---|---|---|
| Lampy Primary plugin | Connected; filesystem, shell execution, Git and service probes available | Execution host interface for authorized QA/build work | Project adapter; root execution must remain allowlisted and audited |
| Gwen (small local model on Lampy; user-identified) | Available in local stack; known by user to produce hallucinations and false positives | Optional low-cost hypothesis/summarization assistant only | Never authoritative; deterministic checks and pipeline-owned analysis establish facts; corroborate consequential alerts; measure precision/recall before expanding role |
| Remote Arc | Read-only paired-device inspection; connected-app discovery/actions | Host observation and permitted external app integration | Use for read-only device inspection; do not treat it as a write/exec path |
| GitHub connector | Authenticated as kitcosby; repository read/write permissions surfaced | Source baseline, branch/PR review, commit/tag identity, issue linkage | GitHub adapter; no merge/push without task-specific approval |
| gpt-queue | Operational queue, standing brief, evidence directory and outbox; not a Git repository | Human work coordination and durable handoff | Keep as queue/ops record; do not install runtime core here |
| qa-ceg | Dedicated CEG parser/generator, suite artifacts, QA scripts and graph format | BibleApp CEG/test adapter | Reuse existing tools; preserve CEG-PARADIGM-CLEANUP gate |
| BibleApp / bible-project / BibleApp-pwa | Distinct repositories and deployment/data boundaries | First project adapter and non-production pilot | Preserve each repo's own build, test and deployment semantics |
| lampy-admin | High-privilege Lampy web/SSH administration console | Operational status context only | Do not embed general orchestrator in privileged admin console |
| Notion Projects / Project Tasks | Documented as PM system of record in queue task 7 | PM/task metadata adapter, if connector access and scope permit | Read-only inventory first; no duplicate PM database |
| Daily project operations and QA automation | Active, daily 9 AM America/Los_Angeles; includes Desktop Commander watch, read-only YLT check, CEG preflight/full subject to gate | Future supervisory trigger and report delivery | Extend only after MVP and notification tests; do not create duplicate |
| Muse outbox | Documented one-file-per-message channel; Muse-side watcher polls about every five minutes | Operational completion/blocker notification | Preferred current Muse handoff, pending watcher delivery verification |
| James mail server | Installation and SMTP configuration present; no James process, no SMTP listener, no Supervisor program entry found | Potential email transport, not presently operational | Discovery only; do not send or change service until configured and tested |
| Gmail via Remote Arc | Connector discovery showed zero connected Gmail accounts | Potential email transport | Not currently available through connected account |
| WhatsApp via Remote Arc | Provider exists in action catalog; no connection was established in this batch | Possible future Muse notification route | Requires connected account, recipient identity/consent and tested delivery |

## 2. Remote host capability snapshot

Read-only Remote Arc inventory at 2026-11-12 22:59 UTC:
- Lampy (Linux x64, agent 0.7.0): connected/online; 4,919 MB total memory, 4,103 MB available, CPU 19.8%; execution health unknown; Remote Arc exposes read-only file/process tools; background agent disabled; execution mode foreground.
- ToE (Windows x64, agent 0.7.0): connected/online; 7,863 MB total memory, 3,194 MB available, CPU 39%; execution health unknown; Remote Arc exposes read-only file/process tools; background agent disabled; execution mode foreground.
- The Lampy plugin remains the available write/exec route, and its shell runs as root. This is powerful but not an isolated runner.

**Runner recommendation:** use Lampy only for on-demand, explicitly allowlisted non-production pilot runs in a dedicated workspace. Do not install a persistent daemon or schedule long-running workers yet. Remote Arc is currently an observation channel, not the execution engine. Reassess host isolation and capacity before parallel test fan-out.

## 3. Repository boundary recommendation

**Leading recommendation: a dedicated repository for the reusable RAD core**, separate from project repos and from the gpt-queue operations folder.

Why:
- lampy-admin is a high-privilege operations console and exposes administrative capabilities; mixing lifecycle orchestration into it would couple unrelated trust boundaries.
- qa-ceg is a specialized CEG and test-generation engine; keep it as an adapter/tool.
- BibleApp and bible-project are project implementations and should consume the common pipeline rather than own it.
- gpt-queue is not a Git repository and is intentionally the coordination/evidence surface.

Candidate name: rad-pipeline (provisional, not created).  
Repository creation and runner placement remain explicit Kit decisions. No repository has been created.

## 3. Existing queue task mapping

| Queue task | Pipeline stage/component | Dependency or gate | Integration outcome |
|---|---|---|---|
| 1. CEG-RESUME | Test adapter / XML result parser / evidence | Current CEG state and exact suite inventory | First CEG adapter acceptance fixture |
| 2. FUNNEL-AUTHORING-CLIENT | Design -> implementation -> staging test -> reconciliation | Staging first; BibleApp-pwa main merge is production deploy and needs Kit go | Example feature-delivery cycle |
| 3. PR33-TOCTOU-FIX | Finding -> implementation correction -> security regression -> PR | New PR only; do not merge without Kit approval | Security finding and regression adapter |
| 4. HARDEN-GATEWAY-CONNECTION | Infrastructure adapter / policy gate / smoke test | Duplicate linked-account removal is NEEDS-KIT | Tool permission and audit evidence contract |
| 5. CEG-PARADIGM-CLEANUP | CEG artifact audit and model reconciliation | Must follow task 1; blocks all new CEG generation/suite regeneration until DONE | Hard policy gate in CEG adapter |
| 6. QA-LEDGER-REVERIFY | Finding registry / retest / supersession | Current production behavior only; no writes; Kit adjudication for QA-0003 preserved | Legacy finding migration and closure proof |
| 7. PM-DESIGN-DOCS | Requirements/decision source inventory | Notion is PM system of record; review-only | Requirements and project metadata adapter |
| 8. SYSANALYSIS-DOCS | Artifact registry / architecture reconciliation | Review-only; verify against live systems | Context/DFD/ERD inventory and drift findings |
| 9. TEXT-DIAGRAMS | Artifact verification / Mermaid validation | Review-only; diagrams must match prose and system | Diagram validation worker |
| 10. QUEUE-EXPIRY-NOTIFICATIONS | Reporter/notifier and scheduler | Explicit expiry rule, verified route, tests, Kit approval before automation change | Later operational integration; not a prerequisite for core |
| 11. POST-MERGE-SDLC-RECONCILIATION | Full cycle orchestration | Build identity -> tests -> triage -> parallel audits -> corrections -> regression -> approval | First end-to-end pipeline pilot specification |
| 12. RAD-PIPELINE-IMPLEMENTATION | Reusable core, contracts, scheduler, adapters, acceptance | Repository/host decision; existing queue priorities and gates remain | This architecture/implementation work package |

## 4. Critical-path implications

1. The CEG gate is real and must be enforced by policy, not merely mentioned in reports. Task 1 precedes task 5; task 5 must be DONE before new graph generation or suite regeneration.
2. Task 11 is the closest existing end-to-end pilot definition. The reusable pipeline should eventually execute that workflow, not create a parallel SDLC checklist.
3. Tasks 7-9 provide artifact inventory and quality checks that feed the artifact registry. They are useful seed data for requirements, system analysis, diagrams and documentation.
4. Tasks 3 and 4 provide security and gateway integration cases for policy enforcement and regression.
5. Task 10 is a separate operational concern. It should not block the MVP; its current transport routes are not yet verified.
6. The current GPT-BRIEF work loop says take the single lowest-numbered READY task. That is serial queue behavior and conflicts with enabling multiple independent queue workers. Before concurrency is enabled, the queue contract must be deliberately revised to support dependency-aware claims/leases, conflict locks, ownership and recovery. Until then, preserve the existing serial claim rule; do not run competing workers against the same queue.

## 5. Recommended first pilot

Use BibleApp staging/QA with the existing qa-ceg and API test interfaces, but begin with a no-write fixture and an immutable baseline. Prove:
- one build baseline;
- at least two independent test jobs;
- stable evidence;
- one finding linked to code plus a README or architecture artifact;
- a requirement ambiguity gate;
- a deliberately blocked CEG action while cleanup is not DONE;
- a regression rerun and a report.

The pilot must not write production data, restart services, generate CEG suites before the gate, merge or deploy.

## 6. Current unresolved decisions

- Kit to select/approve the canonical repository (dedicated rad-pipeline is recommended).
- Kit to select/approve the non-production runner host.
- Resolve serial queue loop vs dependency-aware concurrent claims before enabling multiple workers.
- Define requirement/design source-of-truth rules for cross-project use.
- Define evidence retention and long-term store after the filesystem MVP.
- Define queue expiry semantics and approve a verified email/WhatsApp route.
