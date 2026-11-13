# RAD Pipeline — Core Contracts v0.1

These contracts define the boundary between the reusable core and project-specific adapters. Field names are normative for the MVP; implementations may add optional metadata without changing existing meanings.

## Identifier rules
- project_id: stable slug, e.g. bibleapp.
- cycle_id: unique ID for one development/verification cycle.
- run_id: unique ID for one orchestration attempt.
- stage_id: stable logical stage name.
- attempt: positive integer, increments on retry.
- finding_id: stable ID, e.g. FND-date-sequence.
- artifact_id: stable project-local identifier, not merely a mutable filename.
- revision: immutable commit, tag, content hash or version identifier.

## Cycle record
Required: schema_version, project_id, cycle_id, created_at (RFC 3339 UTC), intent, baseline (repository/build/environment identity, initially pending), state, policy_profile, artifact_inventory_ref, approval_refs, open_findings.

## Stage record
Required: stage_id, cycle_id, run_id, attempt, kind, state, depends_on, inputs, outputs, actor, started_at, completed_at, command_ref and exit_code when executable, policy_decision_ref.
Kind values: design, build, test, audit, reconcile, correction, regression, acceptance, release.

## Artifact record
Required: artifact_id, project_id, type, canonical_location, revision, content_hash when available, authority, valid_from and optional supersedes.
Types: requirement, acceptance_criterion, architecture, context_diagram, dfd, erd, interface, ceg, test, source, config, readme, repository_description, package_description, service_description, operating_instruction, evidence, approval.
Authority values: approved, observed, generated, proposed, unknown.

## Finding record
The JSON Schema is schemas/finding.schema.json.
- A finding may carry multiple classifications.
- Expected behavior must cite an approved requirement/decision, or be marked unresolved.
- Every finding links to the originating test/run or explicitly identifies a non-test discovery.
- Artifact links state relationship: contradicts, stale, missing, implements, verifies, models, describes, depends_on.
- A finding closes only with verification evidence against a named baseline.
- A superseded finding retains lineage and its superseding decision.

## Evidence record
Required: evidence_id, cycle_id, run_id, stage_id, class, source, captured_at, actor, summary, raw_output_ref where applicable, sha256 where applicable, limitations, related_artifact_ids.

For API/test evidence, include where applicable: service/base identity (without credentials), HTTP method and path/route, environment, request timestamp, request/correlation ID, transport/TLS outcome, duration, HTTP status, selected non-sensitive headers, content type, response byte count/hash, redacted raw-body reference, parse/schema verdict, semantic assertion results, expected-vs-actual summary, retry/attempt metadata, and whether the operation is safe to retry. A command exit code or 2xx status without body/result inspection is insufficient evidence of success. Secrets and sensitive payload fields must be redacted before persistence.
Evidence classes: VERIFIED, DEMONSTRATED, ATTESTED, INFERRED.

For model-assisted observations, additionally record (when applicable): model/tool identity and version, prompt or rule-set revision, whether the output is unverified, the exact source evidence supplied, independent corroboration method/result, reviewer disposition, and known limitations. Model-generated summaries are never source evidence and cannot alone create a VERIFIED or DEMONSTRATED record. Distinguish raw observation from model interpretation and from final disposition.

Evidence is append-only. Corrections are new records that explicitly supersede prior records.

## Project adapter contract
Conceptual operations:
- describe_project()
- inventory_artifacts()
- resolve_baseline(revision_or_deployment_ref)
- verify_build_identity(baseline)
- plan_tests(baseline, policy_profile)
- execute_test(test_spec, run_context)
- parse_test_result(raw_result)
- classify_artifact_links(finding, inventory)
- evaluate_policy(action, context)
- verify_artifact(artifact, baseline, expected_contract)
- render_acceptance_report(cycle)

Each adapter declares allowed commands and working directories; read/write capabilities; environment variables allowed (never secret values); resource/time limits; production/non-production targets; approval requirements; project-specific acceptance gates.

## Execution safety
- Commands are structured argv, not interpolated shell strings, except explicitly reviewed adapter scripts.
- No command runs outside declared working directories.
- No secrets in logs, reports, evidence or prompts.
- Each task has timeout, output cap, cancellation and bounded retry policy.
- A timeout or parser error is not a passing test.
- Unknown policy result is a deny.
- Idempotency key is stable across retries of the same intended operation.
