# WP2 — Contracts and evidence store

Implements WP2 of `seed/docs/IMPLEMENTATION-PLAN.md`: versioned JSON
schemas, schema validation with compatibility tests, an append-only
hash-chained evidence writer, and secret redaction before persistence.

Environment: Python 3.12.3, `jsonschema` 4.10.3 (already installed on
this VM — used for draft 2020-12 validation). Tests use stdlib
`unittest` because `pytest` is not installed. No other dependencies.

## What was built

### Schemas — `schemas/`
All are JSON Schema draft 2020-12, `$id` under
`https://schemas.local/rad-pipeline/`, and every record carries
`schema_version` (const `"0.1"`, following the provided finding schema).

| File | Contract source |
|---|---|
| `cycle.schema.json` | CONTRACTS.md "Cycle record"; `state` enum from STATE-MACHINE.md; `SUPERSEDED` requires `successor_cycle_id` (side-state rule); a `recorded` baseline must carry at least one of commit/tag/build_id/deployment_id |
| `stage.schema.json` | CONTRACTS.md "Stage record"; `kind` enum from the contract; `command_ref` and `exit_code` must appear together ("when executable") |
| `finding.schema.json` | **Byte-identical copy** of `seed/schemas/finding.schema.json` — field names unchanged |
| `artifact-link.schema.json` | The `affected_artifacts` entry shape from the finding schema, standalone (see Q9) |
| `approval.schema.json` | Minimal approval record (see Q3) |
| `evidence.schema.json` | CONTRACTS.md "Evidence record", including the optional `api` block (API/test evidence fields) and `model` block (model-assisted observation fields); `class` enum VERIFIED / DEMONSTRATED / ATTESTED / INFERRED; `sha256` fields pinned to 64 lowercase hex |

All schemas set `additionalProperties: false` (see Q8) and are
meta-validated at load time.

### Validation — `radpipe/validate.py`
`check(record, kind) -> list[str]` returns every problem as a specific,
path-qualified string (`$.state: 'SHIPPED' is not one of [...]`,
`$: 'intent' is a required property`); `validate(...)` raises
`ValidationError` carrying the same list. Kinds: `cycle`, `stage`,
`finding`, `artifact_link`, `approval`, `evidence`. Beyond the schema
itself, properties declared `format: date-time` are checked as real
RFC 3339 timestamps (jsonschema does not enforce `format` unaided), and
a stage whose `completed_at` precedes its `started_at` is rejected.

### Evidence store — `radpipe/evidence.py`
Append-only JSONL. Each line is an envelope
`{"seq", "prev_hash", "hash", "record"}` where `hash` is the SHA-256 of
`prev_hash` + the canonical JSON of the record; the first record chains
to a genesis hash of 64 zeros. `EvidenceStore.append()` redacts, then
validates, then appends with flush + fsync — the file is only ever
opened in append mode, and appending to a store that fails verification
is refused. `verify()` / `verify_file()` detects edited records (hash
mismatch), deleted or reordered records (sequence / chain break), and
malformed lines. Corrections are new records using the schema's
`supersedes` field; prior records are never mutated.

### Redaction — `radpipe/redact.py`
Applied in the evidence writer's path before validation and
persistence, and usable standalone. Two rules, recursive, non-mutating:

1. **Key rule** — a mapping value is replaced with `***REDACTED***`
   when its key contains `KEY`, `TOKEN`, `SECRET`, `PASSWORD` or `AUTH`
   (case-insensitive substring, per the WP2 text; see Q6).
2. **Value rule** — credential-shaped substrings are redacted wherever
   they appear: PEM private-key blocks, AWS access key ids (`AKIA…`),
   GitHub token prefixes (`ghp_`, `github_pat_`, …), `Bearer …`
   tokens, passwords embedded in URLs, and JWTs.

## Tests

Run (offline, from this directory):

```
cd ~/workspace/rad-pipeline/work/wp2
python3 -m unittest discover -s tests -v
```

Result on 2026-11-12 (this VM):

```
Ran 44 tests in 0.099s
OK
```

Breakdown: `test_validate.py` 20 (all six fixtures validate; one test
per rejection class — missing field, wrong type, unknown enum ×2,
unknown schema version, additional property, ID pattern, bad and
impossible date-times, bad sha256, below-minimum attempt, empty and
duplicate classifications — plus the conditional rules for superseded
cycles, recorded baselines, and command_ref/exit_code pairing);
`test_redact.py` 10 (secret keys, planted fake GitHub token in an
innocent field, Bearer/URL-password/private-key/AWS/JWT shapes, input
immutability); `test_evidence_store.py` 11 (chain verifies, linkage and
sequence, append-only byte-prefix property, invalid record refused,
edited/deleted/reordered records detected, tampered chain cannot be
extended, planted token never reaches disk); `test_compat.py` 3 (WP2
finding schema byte-identical to the seed's; the current finding
fixture validates against both the seed schema and the WP2 schema).

## Open questions for the owner (ambiguities — not resolved by invention)

- **Q1. Stage `state` vocabulary.** CONTRACTS.md requires a stage
  `state` but enumerates values nowhere (STATE-MACHINE.md is
  cycle-level). The schema accepts any non-empty string. What is the
  stage-state enum (e.g. pending/running/completed/failed)?
- **Q2. Which stage kinds are "executable"?** The contract requires
  `command_ref`/`exit_code` "when executable" without saying which of
  the nine kinds that covers. Encoded instead as an invariant —
  the two fields must appear together — pending a kind-based rule.
- **Q3. Approval record shape.** CONTRACTS.md references approvals
  (`approval_refs`, `decision_refs`, recorded release authority) but
  never enumerates approval fields or an `approval_id` format. The
  schema's minimal set (approval_id, project_id, cycle_id, action,
  decision approved/denied, approver, decided_at) is a guess to be
  confirmed or replaced.
- **Q4. Cycle `baseline` shape.** Modelled as an object with
  `status: pending|recorded` plus identity fields mirroring the
  finding schema's baseline. Should it instead be a reference (like
  `artifact_inventory_ref`), and which identity field is mandatory
  once recorded?
- **Q5. `policy_profile` vocabulary.** No profile names are defined
  anywhere in the seed; the schema accepts any non-empty string.
  Should profiles be an enum?
- **Q6. Redaction key-matching breadth.** The WP2 text's `*AUTH*` and
  `*KEY*` substring rules also redact innocuous keys (`author`,
  `monkey`, `token_count`). Implemented literally; is word-boundary or
  exact-suffix matching intended instead?
- **Q7. Evidence `limitations` type.** Modelled as an array of
  strings; CONTRACTS.md lists the field without a type (a single prose
  string is the alternative reading).
- **Q8. Extension metadata vs closed schemas.** CONTRACTS.md says
  implementations "may add optional metadata", but the one concrete
  schema provided (finding) sets `additionalProperties: false`. All
  WP2 schemas follow the finding schema (closed). Should extensions be
  allowed, e.g. under a dedicated `metadata` object?
- **Q9. Artifact-link versioning.** Links embedded in a finding may
  not carry extra properties, so the standalone artifact-link schema
  makes `schema_version` optional (present in the standalone fixture,
  absent in embedded links) to keep the two forms compatible. Should
  links be independently versioned at all?
- **Q10. Required-but-nullable stage fields.** `completed_at` and
  `policy_decision_ref` are required by CONTRACTS.md but cannot have
  real values for a stage that has not finished / not yet been
  policy-checked; both are modelled as string-or-null. Is that the
  intended reading, or should in-flight stages simply not be recorded
  until complete?
