# Architecture-Led Rapid Application Development Pipeline

Status: DESIGN BASELINE v0.1  
Owner: Kit (architecture and release authority)  
Operational partner: Muse  
Initial pilot: BibleApp estate  
Design intent: reusable across projects; project-specific adapters preserve local rules.

## 1. Purpose

Provide a rapid, architecture-led, evidence-driven development pipeline. Minimize artificial process boundaries while retaining explicit requirements, design authority, traceability, verification and release controls.

This is not Scrum automation. It does not prescribe sprint ceremonies, story points, fixed roles or time-boxed delivery. Work is organized by dependency, risk, evidence and available parallelism.

## 2. Governing principles

1. Architecture before uncontrolled implementation. Establish the problem, requirements, system boundaries, interfaces, data and acceptance conditions before dependent work begins. Design may evolve as evidence arrives.
2. Short feedback loops. Build and verify small coherent increments as soon as dependencies permit.
3. Dependencies, not ceremonies, determine order. Execute independent work concurrently; serialize only where a real dependency or shared decision requires it.
4. Evidence is the control plane. No stage advances on an unsupported assertion. Record exact revisions, environment, commands, results and provenance.
5. One finding can affect many artifacts. A runtime failure may reveal defects in code, requirements, system analysis, CEGs, tests, READMEs, repository metadata or service descriptions.
6. Intent is authoritative; behavior is evidence. Existing behavior and passing tests do not automatically redefine approved requirements.
7. Documentation is a deliverable. README files, repository/package/service descriptions, setup/run/test instructions and architecture artifacts are part of acceptance.
8. Human authority remains explicit. Ambiguous intent, semantic model changes, production changes, merges and releases remain gated by project approval rules.
9. Project autonomy. The common core orchestrates work; project adapters define repositories, environments, tests, artifacts and acceptance rules.
10. Safe failure. Missing evidence, stale baselines, tool disagreement, permission failure or unknown state stops the affected transition; it does not silently degrade to success.

## 3. Logical architecture

- Orchestrator: evaluates state, prerequisites, concurrency limits, claims, retries and stop conditions.
- Project adapter: supplies repository/build identity, environments, test commands, artifact inventory, policy gates and deployment identity.
- Artifact registry: indexes requirements, design documents, diagrams, CEGs, source locations, tests, READMEs and descriptions.
- Execution workers: run authorized build/test/review tasks. Workers may be human, automation or agent-backed.
- Finding/reconciliation service: creates durable findings and maps each finding to all affected artifacts and owners.
- Evidence ledger: immutable run records, raw outputs, hashes, versions, decisions and provenance.
- Policy gate: enforces project-specific approvals, protected operations, branch/merge/deployment rules and CEG prerequisites.
- Reporter/notifier: creates run summaries, blockers, completion notices and approved notifications.

The first implementation should be a small modular application, not a distributed microservice system. Keep modules separable behind explicit contracts; do not introduce queues, databases or services until measured load requires them.

## 4. Lifecycle and state model

Primary lifecycle:
INTAKE -> DESIGN_READY -> IMPLEMENTATION_READY -> BUILT -> BASELINED -> TESTED -> TRIAGED -> RECONCILING -> CORRECTED -> REGRESSION_VERIFIED -> ACCEPTANCE_READY -> RELEASED

Side states:
- WAITING_FOR_INPUT: required intent/decision unresolved.
- BLOCKED: prerequisite, environment, access or dependency unavailable.
- FAILED: a stage ran and failed its acceptance condition.
- CANCELLED: explicitly cancelled by an authorized owner.
- SUPERSEDED: replaced by a newer cycle or baseline, with lineage retained.

Every transition records prior/new state, actor, timestamp, cycle ID, prerequisite evidence, policy decision and resulting evidence reference. No transition is implied by elapsed time. Retries create new attempt records; they never overwrite prior evidence.

## 5. Dependency and concurrency model

The orchestrator builds a directed acyclic dependency graph for each cycle. A task is runnable only when all hard prerequisites are satisfied and its policy gates pass.

Typical sequence:
1. Resolve scope and approved requirement intent.
2. Freeze baseline identity and build the candidate.
3. Run independent test suites concurrently within resource limits.
4. Consolidate and classify results.
5. Launch independent artifact audits concurrently: code/runtime, requirements, architecture/system analysis, CEGs/test models, READMEs/descriptions/operating instructions.
6. Reconcile shared assumptions and obtain decisions for ambiguities.
7. Apply independent approved corrections in parallel; serialize conflicting edits.
8. Run affected tests and integrated regression.
9. Verify cross-artifact traceability and documentation.
10. Obtain release approval and publish an evidence-backed acceptance report.

Parallel workers share finding IDs and a common baseline. They do not independently change authoritative requirement intent or shared interfaces.

## 6. Finding model

Every finding receives a stable ID and records:
- observed condition and expected condition;
- source test, run and exact build baseline;
- classification(s): implementation, requirement, architecture/system-analysis, CEG, test-harness, documentation/description, environment/configuration, security or inconclusive;
- severity, confidence and reproducibility;
- affected artifacts and traceability links;
- proposed disposition and dependencies;
- owner, status, decision record and verification evidence.

A finding may have multiple classifications and affected artifacts. Do not force one root-cause category where evidence supports several.

## 7. Artifact and traceability model

The registry links:
requirement -> design element -> implementation element -> test -> finding -> correction -> verification -> release

Artifact types include requirements and acceptance criteria; context diagrams, DFDs, ERDs, interface/data contracts and architecture decisions; CEG source, generated suites, effects and requirement mappings; source code, configuration and build/deployment manifests; unit, integration, API, security and regression tests; README files, repository descriptions, package/service descriptions, operating instructions; evidence and approval records.

Links are versioned. Each cycle records artifact revision/hash, not just a mutable path. Missing links are reported as traceability gaps, not silently inferred.

## 8. Evidence and audit requirements

Each run record includes cycle/run/stage IDs and timestamps; repository, branch, commit, tag and working-tree state; build artifact identity/hash and deployment identity where relevant; environment/configuration fingerprint with secrets redacted; tool/runtime versions and exact commands; exit codes, counts, raw output references and content hashes; test suite identifiers and result classifications; worker/actor and approval provenance; unresolved discrepancies and limitations.

Evidence classes:
- VERIFIED: directly inspected.
- DEMONSTRATED: executed and observed.
- ATTESTED: reported by an identified operator/source.
- INFERRED: reasoned but not directly verified.

Do not promote an attestation or inference to a demonstration.

### Independent analysis and model trust boundary

The pipeline is evidence-led, not model-led. Local deterministic checks are the primary monitoring mechanism; language models are optional assistants for summarization and hypothesis generation, never authorities for system state or acceptance.

- Gwen is a small local model with a known risk of hallucination and false positives. Treat its outputs as unverified leads, not findings or ground truth.
- Prefer direct, deterministic observations: exit codes, structured test reports, exact file/revision hashes, process and port probes, schema validation, API request/response evidence, and reproducible command output.
- API monitoring must distinguish DNS/connectivity/TLS/timeout failures, HTTP status failures, authentication/authorization, rate limiting, server/dependency errors, malformed protocol responses, schema/contract violations, and semantically incorrect successful responses. A 2xx status alone is never proof of API correctness.
- Read and analyze actual API/test results, not merely whether a command ran or returned an exit code. Inspect status, relevant headers, response body, schema, required fields, semantic assertions, counts and timing against an explicit expected contract. Preserve redacted raw response evidence (or a secure reference plus hash), request identity, endpoint/method, timestamp, environment, correlation/request ID, parser verdict and assertion outcomes. Never persist credentials, tokens, or unredacted sensitive payloads.
- Handle timeouts, empty/truncated bodies, unexpected content types, invalid JSON/XML, partial results, and contradictory status/body combinations as explicit failures or inconclusive outcomes—not passes. Retry only under a declared policy; do not automatically replay non-idempotent requests.
- Preserve raw observations and provenance so the pipeline's own analysis can independently recompute conclusions. A model summary must never replace source evidence.
- For consequential alerts, require a deterministic corroborating check or a human/independent review. Agreement between two language models is not independent verification.
- Separate observation, interpretation, and disposition. An alert is not a confirmed defect; a confirmed defect is not automatically an approved correction.
- Measure false-positive and false-negative rates against a labeled corpus before expanding any model's role. Track abstentions and inconclusive cases; do not optimize only for alert volume.
- Fail closed when evidence is missing, contradictory, stale, or not reproducible. Do not let model confidence override contradictory observations.
- Test every specified maximum at max-1, max and max+1, including search-field character limits and requirement limits. Record the requirement-defined outcome at each point (accept, reject, truncate, normalize, or validation error); do not assume a universal policy.
- Where applicable, test null, zero, omitted and empty values as distinct inputs. Their meaning and expected behavior are field- and requirement-dependent; zero is not inherently invalid, and explicit null is not interchangeable with an omitted field.
- Triage discrepancies against approved intent before changing implementation. A working feature may be misdocumented or mis-tested; correct the README/test when that is the actual defect. Conversely, do not use documentation edits to excuse implementation that violates approved requirements. Requirements themselves may be incomplete or questionable and must be flagged for owner resolution.
- Keep model invocation selective: use it only where semantic interpretation adds value after deterministic checks. This is a design hypothesis for reducing token use, not a claim that local inference is always cheaper or more accurate.

## 9. Safety and authority boundaries

The core cannot override project policy. Default-deny operations include production data changes, production deployments, service restarts, merges, destructive actions, credential changes and semantic changes to requirements/CEGs. Such actions require the exact project's recorded approval and, where specified, the two-key rule.

For this estate:
- preserve existing Kit approval and two-key rules;
- no direct commits to protected branches;
- no merge without Kit's recorded go; use merge commits and required tags;
- BibleApp-pwa main merges are production deployments;
- never write production database data;
- no CEG generation or suite regeneration until CEG-PARADIGM-CLEANUP is DONE;
- NEEDS-KIT and BLOCKED remain hard stops;
- notifications prompt review only; they never resume work or bypass gates.

## 10. Project adapter boundary

A project adapter supplies project identifier and canonical repository set; source-of-truth requirements/design/artifact locations; build and deployment identity probes; authorized build/test commands and resource limits; test result parsers and expected result contracts; artifact inventory and traceability extraction rules; protected operations and approval policy; acceptance criteria and report recipients/routes.

The core must not hard-code BibleApp paths, ports, CEG rules or Vercel behavior. Those belong in the BibleApp adapter.

## 11. Initial deployment topology

Start as a single-process modular runner on an approved development/QA host, with filesystem-backed append-only run/evidence records for the MVP; versioned JSON contracts; a declarative project adapter file; subprocess execution with timeouts, bounded output and explicit allowlisted commands; a dependency scheduler with bounded concurrency; human approval checkpoints; Markdown/JSON reports.

Do not initially add a production daemon, database, message broker, container fleet or automatic deployment. Reassess only after an end-to-end pilot measures a real need.

## 12. Acceptance definition

The MVP is accepted only when a non-production pilot can:
1. establish and record an exact immutable source/build baseline;
2. execute two or more independent authorized test jobs concurrently;
3. preserve run evidence and hashes reproducibly;
4. create one finding linked to at least two distinct artifact types;
5. produce parallel audit work items with a shared finding/baseline;
6. block a dependent correction when requirement intent is unresolved;
7. enforce a deliberately failing policy gate (e.g. CEG cleanup gate);
8. rerun affected tests and a regression set after approved corrections;
9. identify stale/missing README or architecture artifacts as findings;
10. generate a complete acceptance report with unresolved issues and no unauthorized merge/deploy;
11. exercise applicable max-1/max/max+1 boundaries and distinct null/zero/omitted/empty cases with expected outcomes traced to requirements;
12. demonstrate documentation-first triage on fixtures where implementation is correct but its README or test expectation is wrong, without changing the correct implementation.

## 13. Open design decisions

- canonical implementation repository and owner;
- whether the first runner executes on Lampy or a separate development host;
- source-of-truth for requirements/design artifacts across projects;
- exact schema evolution/versioning policy;
- concurrency/resource limits per host and suite;
- long-term evidence retention and storage;
- approved email route and Muse recipient identity;
- whether queue expiry should be time-based or event/state-based (must be owner-defined).
