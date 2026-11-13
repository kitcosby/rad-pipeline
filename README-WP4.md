# WP4 — First project adapter (BibleApp QA)

Implements WP4 of `seed/docs/IMPLEMENTATION-PLAN.md`: the first
project adapter. It integrates the BibleApp git baseline, staging
build/runtime identity probes, the requirements/architecture
inventory, and the project's existing QA batteries — with the CEG
generation gate enforced by policy, and no production contact.

Built on the merged WP2+WP3 code: the WP3 tree's `radpipe/` core and
`schemas/` were copied into this tree **unmodified** (the wp2/wp3
trees are untouched); everything under `radpipe/adapters/` is new.
Environment: Python 3.12.3, `jsonschema` 4.10.3, stdlib `unittest`.
Fully offline.

## What was built

### `radpipe/adapters/probe.py` — deterministic probes + probe CLI
The scheduler's per-attempt evidence carries command, verdict and an
output hash, but not the captured values a baseline report needs
(WP3 Q8). Probes therefore run as scheduler tasks through this CLI:
each probe writes a machine-readable JSON result into the run's work
directory, and the adapter afterwards appends evidence records
carrying the exact values, hashed.

- `git-baseline` — branch, HEAD commit, full tag list, working-tree
  state with verbatim `git status --porcelain` entries. Executed
  through the WP3 executor with an allowlist of exactly `{"git"}` and
  a fixed read-only command set (`rev-parse`, `status`, `tag`,
  `log`); nothing that can mutate a repository is ever invoked.
- `http-identity` — one endpoint check with the WP2A failure
  taxonomy. Expected status, content markers and (when declared) JSON
  keys are all asserted — a 2xx alone never counts as success.
  Classifications: `ok`, `transport`, `tls`, `timeout`, `http`,
  `auth` (401/403), `rate_limit` (429), `server` (5xx), `protocol`,
  `schema` (bad JSON / missing declared keys), `semantic` (missing
  content markers). The result includes status, content type, byte
  count, response SHA-256, duration, per-assertion outcomes and a
  capped body excerpt.
- `inventory` — artifact enumeration (CONTRACTS.md artifact records):
  README* files → `readme`; a root DESCRIPTION/description file and a
  non-default `.git/description` → `repository_description`;
  package.json with a description → `package_description` (without →
  `config`); Markdown under `docs/` → `architecture`; `*.ceg` →
  `ceg`. Each artifact carries its SHA-256 content hash as revision.

Probe exit codes: git-baseline exits non-zero when git cannot
establish a baseline (the stage fails closed); inventory exits
non-zero when the root is missing; **http-identity exits 0 whenever
the probe ran and classified** — a dead staging endpoint is a finding
for the report, not a probe malfunction, and must not stop the pipe
before the report exists (see Q2).

### `radpipe/adapters/bibleapp.py` — the adapter
`BibleAppAdapter` assembles one WP3 scheduler cycle:

| Stage | Kind | Contents |
|---|---|---|
| `baseline` | build | the `git-baseline` probe task |
| `identity` | test | one `http-identity` probe task per configured endpoint (run concurrently within the stage) |
| `inventory` | audit | the `inventory` probe task |
| `qa` | test | one task per configured existing QA battery (argv from config, through the allowlist executor) |
| `ceg-generation` | build | only when config requests it; gated by the WP3 `CegGenerationGate`, which the adapter registers |

The run spec's flags carry `ceg_paradigm_cleanup` **from config**;
when the config has no such key the flag is absent, the gate treats
it as not DONE, and generation is denied (and the denial evidenced)
before any generation command can run.

After the pipe runs, the adapter appends its own evidence records —
git baseline `VERIFIED` with exact branch/commit/tags/dirty entries
in the summary, one `DEMONSTRATED` record per endpoint with the WP2
API-evidence block (status, transport outcome, duration, response
hash, assertion results), inventory `VERIFIED` with every artifact ID
linked — and emits the **baseline report**: a dict plus
`render_report_markdown()`. Every reported number is the captured
value and names its evidence record; QA numbers are the scheduler's
own evidenced `TaskResult`s.

### `radpipe/adapters/bibleapp.example.json` — config template
Single JSON config: `repo_path`, `evidence_path`, `work_dir`,
`allowlist`, `python_executable`, `endpoints` (service, url, method,
timeout, environment, expected status/markers/JSON keys),
`batteries` (name, argv, cwd, timeout, retry/idempotency),
`ceg_generation` (requested, argv), `ceg_paradigm_cleanup`,
`inventory` (root, excludes). No Lampy path is hard-coded in code;
relative config paths resolve against the config file's directory.

### `docs/DECISIONS.md`
The repo's full decision log updated: the seed log plus **D-003**
(Kit's standing approval, 2026-11-12 16:30 PT — dual-engine-verified
work packages flow build → verify → branch → PR → merge-commit
without per-step decisions; production/destructive/out-of-class
actions still require Kit; GPT's post-merge evidence reviews are the
review lane) and **D-004** (PR #1 merged as `c2add431`, PR #2 as
`7b64b5a8`, both 2026-11-12; version tags and merged-branch deletion
recorded as manual leftovers, not done).

## Tests

Run (offline, from this directory):

```
cd ~/workspace/rad-pipeline/work/wp4
python3 -m unittest discover -s tests -v
```

Result on 2026-11-12 (this VM), two consecutive runs, identical:

```
Ran 17 tests in ~7.5s
OK
```

- `test_bibleapp_git.py` — 4: probe captures exact branch/commit/
  tags/clean state and exact dirty state (both against an independent
  subprocess-git oracle over a temp repo); non-repo fails closed;
  adapter report git values equal the oracle and trace to the
  evidence record whose hash is the probe result's content hash.
- `test_bibleapp_http.py` — 7 (throwaway `http.server` on an
  ephemeral loopback port): content-marker+JSON-key success with
  exact response hash; HTTP 500 → `server`; connection refused →
  `transport`; missing marker → `semantic`; missing JSON key →
  `schema`; slow endpoint → `timeout`; adapter-cycle identity
  evidence carries the full API block with exact status/hash and
  assertion results.
- `test_bibleapp_cycle.py` — 6: full cycle completes (exit codes,
  counts, five inventory artifacts with oracle-verified hashes,
  cycle-close next intake); report values trace to the evidence store
  (hash equality + record counts + chain verification); a failing
  fake battery records exit code 3 and fails the run; **CEG gate**:
  generation denied by default (no flag in config) with the denial
  evidenced and the fake's marker never written, denied again with
  `IN_PROGRESS`, and permitted with `DONE` (fake runs, marker
  written, cycle completes). CEG generation in tests is a fake
  stand-in script — the real engine never runs.

## Running the LIVE baseline (parent procedure)

The adapter itself is host-agnostic; the live run places this tree in
the D-002 runner workspace on the Lampy distro and runs one baseline
cycle as the unprivileged `radpipe` user. Non-production only.

1. **Deploy the tree** into the runner workspace (code beside, not
   inside, the run data):

   ```
   # in the distro, as root (via the lampy SSH route):
   mkdir -p /home/mcpgw/projects/rad-pipeline/work/rad-pipeline
   # copy this tree's radpipe/ and schemas/ into that directory, then:
   chown -R radpipe:mcpgw /home/mcpgw/projects/rad-pipeline/work/rad-pipeline
   ```

2. **Write the live config** (start from
   `radpipe/adapters/bibleapp.example.json`) at
   `/home/mcpgw/projects/rad-pipeline/work/bibleapp.live.json` with
   the real Lampy staging layout:
   - `repo_path`: `/opt/stage` (the BibleApp staging tree);
     `inventory.root`: `/opt/stage`.
   - `evidence_path`:
     `/home/mcpgw/projects/rad-pipeline/evidence/bibleapp-evidence.jsonl`;
     `work_dir`: `/home/mcpgw/projects/rad-pipeline/work/bibleapp`.
   - `allowlist`: `/usr/bin/python3`, `git`, plus the qa-ceg battery
     entry point under `/home/mcpgw/projects/qa-ceg/` (the gateway
     projects root, per INTEGRATION-MAP).
   - `endpoints`: the staging Flask and staging API health endpoints
     on loopback. **Confirm the staging ports on the host first**
     (the `bible-staging` Supervisor program's config) — the example
     file's 5058/8800 are placeholders; production Flask/API are
     5057/8799 and are NOT staging targets.
   - `batteries`: the permitted pre-existing qa-ceg suites only
     (preflight first); no generation flags.
   - `ceg_generation.requested`: `false` for the first live baseline;
     `ceg_paradigm_cleanup`: leave unset (or the queue's actual
     CEG-PARADIGM-CLEANUP state) — it is not DONE.

3. **Run one baseline cycle as the runner user** (driver script
   writes `report.json` + `report.md` next to the work dir):

   ```
   cat > /home/mcpgw/projects/rad-pipeline/work/run_baseline.py <<'EOF'
   import json, sys
   from pathlib import Path
   sys.path.insert(0, "/home/mcpgw/projects/rad-pipeline/work/rad-pipeline")
   from radpipe.adapters.bibleapp import BibleAppAdapter
   config = sys.argv[1]
   adapter = BibleAppAdapter.from_config_file(config)
   run = adapter.run_cycle()
   out = Path(adapter.work_dir).parent
   (out / "report.json").write_text(json.dumps(run.report, indent=2))
   (out / "report.md").write_text(run.report_markdown)
   print(run.run_result.status, run.report["evidence"])
   EOF
   sudo -u radpipe /usr/bin/python3 \
     /home/mcpgw/projects/rad-pipeline/work/run_baseline.py \
     /home/mcpgw/projects/rad-pipeline/work/bibleapp.live.json
   ```

   A healthy first run ends `completed` with the evidence chain
   verifying; the report lands at
   `/home/mcpgw/projects/rad-pipeline/work/report.md`.

## Provisional choices and open questions for the owner

- **P1 (stage kinds).** baseline = `build`, identity = `test`,
  inventory = `audit`, qa = `test`, ceg-generation = `build`. The
  specs name stage kinds but never assign them to adapter stages.
- **P2 (probe exit semantics).** See Q2.
- **P3 (inventory rules).** The classification rules in probe.py are
  the adapter's; the specs inventory artifact *types* but do not fix
  which files map to which type for this project.

Numbered questions where the specs are silent (no semantics invented):

- **Q1. Staging endpoint ports.** The example config's staging
  Flask/API ports (5058/8800) are placeholders. What are the
  `bible-staging` program's actual loopback ports? (Host confirmation
  from the Supervisor config is required before the first live run
  either way; production 5057/8799 are not staging targets.)
- **Q2. Identity-probe failure semantics.** A failed identity probe
  currently never fails its stage: the cycle completes and the
  failure is a classified report finding. Should a `server` or
  `transport` classification instead fail the identity stage — e.g.
  for acceptance cycles — while baseline cycles keep the
  observe-and-report rule?
- **Q3. Service descriptions.** No `service_description` artifacts
  are inventoried: the rule set has no source for them in the
  BibleApp tree. Where do BibleApp service descriptions live, if
  anywhere?
- **Q4. The permitted battery set.** Which qa-ceg entry points and
  flags constitute the "permitted non-production smoke/regression
  plan" for the first live run — preflight only, or named
  pre-existing suites as well?
- **Q5. Resolved-baseline write-back.** The cycle record's baseline
  stays `pending`; the resolved baseline (repo, branch, commit)
  lives in the adapter report. Should the adapter append a
  superseding cycle record carrying the recorded baseline — and
  should cycle-close carry that forward instead of WP3's verbatim
  carry (extends WP3 Q9)?
- **Q6. CEG flag provenance (extends WP3 Q7).** The adapter passes
  the config's `ceg_paradigm_cleanup` value to the gate verbatim.
  In the live run, who sets it — the operator reading the queue's
  CEG-PARADIGM-CLEANUP task state, or should the adapter read the
  queue/evidence itself?
- **Q7. Probe result retention.** Probe result files (including a
  ≤1000-char response body excerpt) persist in the run work dir;
  evidence records hold only hashes and assertions. What retention
  and redaction rules should apply to work-dir results?
