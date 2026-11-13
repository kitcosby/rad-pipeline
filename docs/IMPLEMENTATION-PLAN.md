# RAD Pipeline — Implementation Plan

Status: proposed execution plan v0.1  
Design style: architecture-led rapid application development  
Pilot: BibleApp, non-production first

## Work packages

### WP0 — Architecture and constraints
Deliverables: ARCHITECTURE.md, CONTRACTS.md, STATE-MACHINE.md, finding schema, project adapter contract, implementation sequence and acceptance criteria.
Exit: owner accepts architecture and unresolved decisions are explicitly recorded.

### WP1 — Repository and runtime placement decision
- Inventory candidate repositories and existing automation entry points.
- Choose a canonical repository (do not put runtime code in the non-Git gpt-queue folder).
- Choose a non-production execution host.
- Verify runtimes, permissions, test dependencies and resource constraints.
- Record owner approval.
Parallel: repository inventory and host capability inventory.
Sequential: implementation begins only after canonical repo/host decision.

### WP2 — Contracts and evidence store
Implement versioned JSON schemas for cycle, stage, finding, artifact link, approval and run evidence; schema validation and compatibility tests; append-only evidence writer with content hashes; redaction rules for secrets and sensitive environment values.
Exit: fixtures validate; malformed/incomplete evidence is rejected; prior records are never overwritten.

### WP2A — Deterministic monitoring and independent analysis boundary
Build monitoring from deterministic probes and parsers first: exact process/port/service observations, repository revisions and working-tree state, hashes, schema checks, test exit codes and structured result counts. Add API checks that distinguish transport, TLS, timeout, HTTP, auth, rate-limit, server/dependency, protocol, schema/contract and semantic failures. Read actual API responses and test results: validate status, headers, body, schema, required fields, semantic expectations, counts and latency; a 2xx response or zero exit code alone is insufficient. Preserve redacted raw response/output evidence, hashes, endpoint/method, request/correlation ID, environment, parser verdict and assertion outcomes. Explicitly classify malformed, empty, truncated, partial or contradictory responses; do not silently pass them. Retry only according to an explicit policy and never blindly replay non-idempotent operations. Persist raw evidence and provenance before any model interpretation. Gwen may propose hypotheses or summaries, but those outputs are unverified leads; the pipeline's own analysis must derive the finding from source evidence. Consequential alerts require deterministic corroboration or human/independent review. Establish a labeled validation corpus and measure false positives, false negatives and abstentions before expanding model use.
Add boundary/value-state test generation: for each defined maximum, cover max-1, max and max+1 (including search-field character limits and requirement limits); where relevant, test null, zero, omitted and empty independently. Derive expected outcomes from approved field requirements, and mark missing/ambiguous expectations unresolved rather than inventing them. Include API-level cases where the value crosses transport, parser, schema and semantic validation layers.
Exit: seeded true/false/inconclusive cases are classified from evidence without relying on Gwen; model output cannot independently advance a state or trigger a protected action; boundary and value-state outcomes are requirement-traceable.

### WP3 — Orchestration core
Implement declarative DAG/task dependencies; state machine and transition guard; bounded parallel execution; timeout/cancellation/retry handling; idempotent task/run identifiers; safe subprocess allowlist and output capture; policy gate interface.
Exit: deterministic scheduler tests prove ordering, concurrency, retries and fail-closed behavior.

### WP4 — First project adapter (BibleApp QA)
Integrate Git source/branch/commit/tag and working-tree baseline; staging build/runtime identity probes; existing QA/CEG batteries through their existing interfaces; requirements and architecture inventory; CEG gate and Kit approval rules; README/repository/service description checks.
Do not run CEG generation until the standing cleanup gate is DONE. Do not modify production.
Exit: adapter reports accurate baseline and can run a permitted non-production smoke/regression plan.

### WP5 — Finding and artifact reconciliation
Implement common finding record; multi-classification and many-to-many artifact links; traceability graph and missing-link detection; parallel review work packages; decision capture for ambiguous requirements; reconciliation report showing code + requirements + analysis + CEG + README/description effects. Triage documentation and test expectations against approved intent and observed implementation before proposing code changes. Include fixtures where code is correct but documentation or a test is wrong, and fixtures where documentation is accurate but implementation violates requirements. Preserve correct features; flag questionable requirements for owner adjudication.
Exit: seeded fixture with one finding spanning at least two artifact types is traced end-to-end.

### WP6 — Regression, acceptance and reporting
Implement affected-test selection plus required regression set; acceptance checklist evaluator; Markdown and JSON reports; unresolved issue and evidence index; release approval gate (no automatic merge/deploy).
Exit: full MVP acceptance matrix in ARCHITECTURE.md passes on a non-production fixture.

### WP7 — Notifications and operations
After core stability: verify Muse outbox watcher and delivery; inspect James service and outbound SMTP safely; verify an authorized email account/recipient; define queue expiry rule with Kit; test deduplication and retries using non-production fixtures; update the existing daily automation only after end-to-end tests and explicit approval.
No WhatsApp or email send during discovery. No automation change during discovery.

## Parallel work map

| Workstream | Can run in parallel with | Must wait for |
|---|---|---|
| Candidate repo inventory | Host inventory, adapter inventory | Nothing |
| Host/runtime capability check | Repo inventory | Nothing |
| Contract/schema implementation | Evidence format review | Architecture contract accepted |
| Scheduler prototype | Schema validation tests | State/dependency contract |
| BibleApp adapter inventory | Core prototype | Project boundary agreed |
| Finding/artifact mapping | Adapter inventory | Artifact registry contract |
| Notification route discovery | WP2-WP6 design/implementation | Does not block core MVP |
| Integrated acceptance | None of its dependent work | All MVP components and fixture |

## Critical path

1. Select canonical repo and non-production host.
2. Freeze versioned contracts and state model.
3. Build evidence ledger and transition guard.
4. Build dependency scheduler.
5. Integrate first project adapter.
6. Implement multi-artifact findings/reconciliation.
7. Run full acceptance fixture.
8. Only then expand to operational notifications and daily automation.

## Delivery controls

- One branch per coherent work package; PR review before merge.
- No direct main-branch commits.
- No merge, production deployment, service restart or data write without the exact required approval.
- Tests and evidence accompany each package.
- Update README and architecture docs in the same delivery as behavior changes.
- Keep a decision log for unresolved architecture choices.
- Use the existing project queue for coordination; do not create a parallel backlog.

## MVP acceptance checklist

- [ ] exact baseline recorded and independently re-readable
- [ ] test jobs execute concurrently within configured limit
- [ ] command, exit code, output and hashes persisted
- [ ] findings have stable IDs and multi-artifact links
- [ ] requirements ambiguity blocks dependent corrections
- [ ] CEG policy gate blocks generation when cleanup is not DONE
- [ ] README and descriptions included in artifact audit
- [ ] affected tests and regression tests rerun
- [ ] acceptance report includes residual risk and unresolved decisions
- [ ] merge/deploy remain human-approved
