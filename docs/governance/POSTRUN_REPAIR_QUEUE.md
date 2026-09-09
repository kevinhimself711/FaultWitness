# Post-run repair queue (pre-G03 close)

Items that can only be applied **after** the live r4 preflight and its live arms finish, because
their targets are hashed at both ends of every run and editing them mid-run self-invalidates it.

Protected during a run (`protected_asset_snapshot`, `g03_readiness.py:2726`):
`docs/audit/**`, `docs/gates/G02/{PLAN,REPORT,VALIDATIONS}.*`, `docs/evals/EVAL-G02-*`.

Also frozen during a run (`_source_inputs_v3`, `g03_readiness.py:2788`) — these are hashed into
`relevant_source_digest`, and editing one mid-run breaks resume:
`src/faultwitness_dev/{g03_readiness,g02_lab,g02_baselines,cli}.py`,
`config/g03/baselines-v3.yaml`, `config/g02/lab.yaml`,
`docs/blueprint/AMENDMENTS/AMD-0007.md`, `docs/gates/G03/PLAN.md`,
`docs/runbooks/G03_BASELINE_READINESS.md`, `tests/g03/test_g03_readiness.py`.

## 1. Broken local link (blocks `verify-fast`)

`docs/audit/2026-07-28/gates/G03.md:394` uses `../../adr/ADR-0016.md` and
`../../adr/ADR-0007.md`. The file lives at `docs/audit/2026-07-28/gates/`, so `../../` resolves
to `docs/audit/`. Both need **three** levels: `../../../adr/ADR-0016.md`,
`../../../adr/ADR-0007.md`. Confirmed by `check_local_links`:

```
broken local link in docs\audit\2026-07-28\gates\G03.md: ../../adr/ADR-0016.md
```

## 2. Host write-off consequences in the audit doc

`docs/audit/2026-07-28/gates/G03.md:286-288` still reads that the 7 `infra_failed` cases
"需要重跑，不需要修" and that post-probe confirmed the host recovered. ADR-0017 supersedes the
second half: those cases are attributable to the failing original host, and that round
(24 pass / 7 `infra_failed` / 1 `metric_fail`) is **not** a baseline to improve on, because the CPU
was silently corrupting execution. The "需要重跑" half stays correct; what changes is that the
re-run happens on different hardware and the old round is not a comparison point.

The prerequisite table at `:229-234` needs **no structural change** — it already carries four rows
with row 4 (`消除组存在性泄漏，令三条 baseline 分化后重跑`) as the sole hard blocker, and states the
acceptance criterion as `no_rag < naive_react` with non-zero CI width. (An earlier draft of this
queue claimed it was three rows; that was wrong.) Only row 4's status cell needs the r5 outcome.

Add a host-stability subsection recording, for the original host: 3112 dumps, 95 distinct RIPs,
crashes on both 5.15 and 5.8, microcode `0x123` → `0x12F` → host no longer POSTs. And for the
replacement host: the 2026-08-12 crash-reboot loop at microcode `0x133`, followed by an
11-day uninterrupted run (booted 2026-08-25, still up at 2026-09-05) with `oops_this_boot=0` and
`mce_this_boot=0`. ADR-0017 is the primary record; the audit note carries the operational
consequence.

## 3. Evidence must record the producing host

ADR-0016 obliges recording which kernel produced each artifact; ADR-0017 extends that to which
**host**. The run manifest currently records `producer_sha`, `relevant_source_digest`, and
`checkpoint_identities` but no host identity. Adding a host field to the manifest touches
`g03_readiness.py`, a frozen input, so it must wait for a run boundary.

## 4. Textual tells in `trace_errors.descriptions` (finding, not a blocker)

`presence_only_probe_v3` (`g03_readiness.py:766`) measures **structural** leakage only — it builds
a signature from which evidence `kind`s are non-empty and checks that a majority-prior classifier
over those signatures scores exactly `top1 == 8` and `top3 <= 20`. It never inspects sample
content. So free-text fields are outside its reach by construction.

Scanning r4's packets, `trace_errors[*].descriptions` carries five distinct strings, two of which
are 1:1 tells for their class across every case observed:

| tell | class | cases |
| --- | --- | --- |
| `Error: Product Catalog Fail Feature Flag Enabled` | `productCatalogFailure` | all, and no others |
| `name resolver error: produced zero addresses` | `paymentUnreachable` | all, and no others |
| `Payment request failed. Invalid token.` | `paymentFailure` + one `emailMemoryLeak` | not clean |

Assessment: **record, do not block.** These are messages the OTel demo genuinely emits when the
flag is set — real telemetry an SRE would see in a real incident, not synthetic label injection —
so removing them would make the packet *less* faithful than production. They are also available
identically to every arm, and the G03 acceptance criterion is the *relative* comparison
`no_rag < naive_react`. A shared trivially-solvable subset compresses that gap rather than
manufacturing it, so it biases against the hypothesis, not toward it.

What it does mean: an absolute core-e2e number on this dataset is not a measure of reasoning for
those 5+ cases, and the deterministic estimator does not read these strings at all (it uses only
`trace_activity.trace_count` and the per-label `root_signal` numeric feature,
`g03_readiness.py:965`). If a future gate wants an absolute claim rather than a relative one, the
honest move is a text-blinded packet variant reported alongside, not deletion of the field.

## 5. Never touch the SOPS store while a run is live

r4 case 26 was lost to a secret-store collision, not to the host or the code. The scenario's first
act is `RemoteFlagClient.read()`, which goes through `run_remote_script(privileged=True)` and
decrypts the SOPS store; an operator health-check doing the same thing ran at the same second, and
the scenario died before taking a single measurement. The retry added below makes this survivable,
not free — it still costs ~18 s, and a sustained collision could exhaust the attempts.

Honest limit on that account: the correlation is exact and the shared-store mechanism is plausible,
but causation was **not proven**. `_run_sops` deliberately discards sops stderr so no secret
material can leak (`bootstrap.py:351`), so the actual reason for the non-zero exit was never
observed. Treat concurrent decrypt as the working explanation.

The rule covers more than remote commands: any privileged remote call decrypts the store, and so
does a local `load_secret_bundle(...)`. While a preflight or live run is in flight, stay off the
store entirely. Read-only unprivileged checks are fine — better still, read the trial journal under
`.audit/g03-readiness/<run>/journals/scenarios/trials/`, which shows progress with no host contact.

Note the trap that hid this for one cycle: an unprivileged `pregate.sh` reports
`readyz=unreachable`, `fw_sut_ready=0`, and `PARSE_FAIL`, which is indistinguishable from a dead
cluster and is really a permission failure. Confirm the check before believing a bad reading, per
CLAUDE.md's 区分"我的检查坏了"和"东西坏了". A genuine host failure shows a *changed boot time*.

## 6. Judgment call to disclose: inheritance versus "fresh replay"

`docs/runbooks/G03_BASELINE_READINESS.md` says a source change "invalidates resume and requires a
new empty directory and fresh replay." I edited source between r4 and r5 (items above), then
launched r5 in a new empty directory but seeded it with r4's 25 passing records rather than
re-measuring them. That is a deliberate reading, and it should be stated rather than left implicit.

The reading: the sentence governs **resume**, and its purpose is that no record may survive a
change to what is being measured. That purpose is satisfied here on evidence, not assertion —
both checkpoint-pinned digests are byte-identical across the edit
(`live_readiness_collector_source_digest` = `b831184c…`,
`live_readiness_observer_source_digest` = `9a918f3a…`), so the collector, observer, oracles,
predicates, thresholds, packet shape, and formulas are unchanged. The edits touch SSH transport
retry and run-directory plumbing only. Every inherited record therefore describes the same
measurement r5 would produce, and each is re-validated against a recomputed semantic `cache_key`
before being reused.

The stricter reading — that any source edit forces re-measuring all 32 — would have cost a full
re-run to reproduce 25 results whose measurement surface provably did not change, and would have
re-exposed the run to the same class of transport failure. If a reviewer prefers that reading, the
remedy is a clean 32-case replay with no `--inherit-passing-trials-from`; nothing about r5's
evidence needs reinterpreting, it would simply be re-earned.

## 7. r5 preflight is blocked on the deterministic estimator, not on leakage (open)

r5 is the **first run to complete the 32-case replay** — r1/r2/r4 and every frozen/diagnostic run
before it died at `scenario_replay_incomplete`, so the deterministic estimator had never once run on
a complete dataset. Leakage is eliminated (presence Top-1 exactly `8/32`, Top-3 exactly `20/32` at
the ceiling, six groups complete on all 32). The two blockers are `ambiguous_cases` (4) and
`deterministic_N_below_32` (28), and the second is caused by the first.

`g03_readiness.py:2985` refuses to resume a blocked preflight, so r5 can never become gate evidence
and the "no source edits after preflight" rule is moot for it. The 32 scenario packets are sound —
only the estimator's reading of them is at issue — so all 32 trials stay inheritable into a
successor run.

### 7a. The memory root signal has no usable absolute threshold

All four ambiguous cases (`SEED-G02-0017/0028/0029/0031`) are truth `kafkaQueueProblems` with the
same single intruder, `emailMemoryLeak`. `email` and `fraud-detection` are both Kafka consumers, so
a Kafka fault really does grow email's working set — this is genuine cross-talk, not a data defect.

`working_set_bytes` is the only root signal with a large non-zero healthy baseline. All 224 memory
samples are exact multiples of 4096 (GCD exactly one page), so AMD-0007's declared memory quantum of
`1` byte overstates the counter's resolution by 4096x. Correcting the quantum alone changes
**nothing** (verified: ambiguity stays 4/N stays 28) because the threshold is a P99 of single-step
healthy *drift*, and 127 of 128 such drifts are exactly zero — the threshold collapses to the
quantum, which is then compared against an excess accumulated across seven windows.

A *relative* floor does separate, and it holds on two independent runs (r5 and the 2026-07-29
diagnostic scan, 56 case-measurements pooled): true email leaks are >= 10.39% of baseline working
set; every non-email case is <= 3.87%. Every threshold from 4% to 10% gives zero false qualifications
and zero missed leaks, so 5% sits mid-plateau rather than on a cliff. This is scale-free, which an
absolute byte threshold cannot be across differently-sized services.

Note the run-to-run instability that makes an absolute threshold hopeless: case 0028's email memory
excess is `-1,085,440` B on 2026-07-29 and `+135,168` B in r5 — same case, same fault class,
opposite sign. Which cases trip the ambiguity flag is therefore partly a coin flip.

AMD-0006's first listed reason for retiring metric v1 was that "the ambient `working_set` field
intercepted three unrelated fault classes." Metric v2 removed the *presence* shortcut but left the
same ambient signal able to intercept through a magnitude threshold. This is that defect's second
generation, not a new one.

### 7b. The larger finding: in 15 of 32 cases the TRUE label cannot qualify at all

Applying the relative floor drops ambiguity to 0 and N to 32 with **zero** change to any of the 28
already-scored cases, but it also revealed that all four true `emailMemoryLeak` cases score
`unknown` — and they did so **before** any change. Their `trace_activity` excess is 1-2 against a
cutoff of 2.0, so the AND-rule rejects them on the activity feature while their root signal passes
by six orders of magnitude. The estimator has never detected a single real email leak; it only ever
qualified `emailMemoryLeak` spuriously, on other labels' cases.

Auditing every case against its own true label: **15 of 32 true labels fail to qualify**, and 9 of
those 15 fail because the `trace_activity` excess *exactly equals* its cutoff (2 vs 2.0, 1 vs 1.0).
`threshold = healthy_p99 + quantum` already reserves one full count of headroom on an integer
counter, and `excess > cutoff` then demands a second full count. That double margin discards real
signal.

Consequence for interpretation: the deterministic point estimate is `0.500` (95% CI
`0.321 - 0.679`, width `0.357`, on the 28 scored rows). That number is substantially a
threshold-arithmetic artifact, not a measure of task difficulty, so it is not a sound comparison
boundary for `no_rag < naive_react` in either direction. Fixing 7a alone would raise it to `17/32`
without touching any previously-scored case.

### Resolution — both fixes applied 2026-09-05 (option B, on the user's explicit decision)

Applied in `g03_readiness.py`, recorded in AMD-0007 under "Amendment of 2026-09-05":

- `RELATIVE_ROOT_SIGNAL_FLOORS = {"emailMemoryLeak": 0.05}`; the threshold registry now stores
  `relative_floor_fraction`, `relative_floor_healthy_median`, and `relative_floor` per case, and the
  threshold is `max(healthy_p99 + quantum, relative_floor)`. Raises the cutoff only.
- `memory_bytes` quantum `1` -> `4096` (page-granular; all 224 samples were exact page multiples).
- Candidate rule `excess > cutoff` -> `excess >= cutoff`.

The decisive check that this is a correction and not a weakening: **false-label qualifications fall
to zero**. r5 goes from 17/32 true + 4 false to 26/32 true + **0** false out of 160 non-truth pairs;
the independent 2026-07-29 scan goes from 14/24 true + 6 false to 19/24 true + **0** false. A
relaxed gate raises the false count.

Preflight now reports zero blockers on r5's packets: ambiguity `0`, `N = 32`, presence Top-1 `8/32`,
Top-3 `20/32`, token `pass`, deterministic `0.8125` CI `[0.656, 0.938]`.

Unchanged and verified: `dataset_digest` `8f5a628ab1eb5e87fd5846194b8d6792`, collector digest
`b831184cf2d95d04`, observer digest `9a918f3aaaf2c30d`. So the measurement surface did not move and
r5's 32 trials remain inheritable. `metric_definition_digest` does change, which invalidates resume
and requires a fresh preflight directory — the replay is minutes of inheritance, not live spend.

Tests: 3 updated/added in `tests/g03` pinning the `>=` rule, the derived (not hardcoded) relative
floor, and the corrected quantum. Suites green: g03 40/40, g02 127/127, ruff clean.

Watch item for the live run: deterministic is now a genuinely stronger baseline, so `best_baseline`
(max across arms, point estimate) has less room under `0.90`. That is the instrument working as
designed. Do not cap the target or exclude the winning baseline to make it fit.

## Already applied (unhashed paths, safe mid-run)

- **`src/faultwitness_dev/g02_lab.py` — bounded transport retry on the flag read.**
  `RemoteFlagClient.read` is the first call `run_readiness_scenario_v3` makes, *before* any
  measurement. `run_remote_script(privileged=True)` opens three SSH sessions with
  `ConnectTimeout=10`, no retry, and decrypts the SOPS store on every call, so a concurrent
  decrypt or momentary SSH refusal discarded a whole case. r4 case 26 failed exactly this way
  (`SOPS operation failed without emitting secret material`) — self-inflicted: an operator
  health-check ran `--privileged` against the same store at the same second. AMD-0003 already
  classifies transport failure as attributable infrastructure, so it is now retried 4× at 6 s.
  Deliberately **not** applied to `write`, where a retry could double-apply a mutation.
  Verified not to disturb either checkpoint-pinned digest (`b831184c…`, `9a918f3a…` unchanged).

- **`src/faultwitness_dev/g03_readiness.py` + `cli.py` — auditable trial inheritance.**
  A preflight requires a new empty directory and there is no in-place retry, so one
  infrastructure failure at case 26 forced re-measuring the 25 cases that had already passed.
  `--inherit-passing-trials-from` seeds a fresh run with only `pass` records **after** the
  empty-directory guard has run, so the guard keeps its force. Safe because `cache_key` is
  semantic (SUT image set, collector contract digest, scenario, SUT producer SHA, window
  counts — not repository state): the replay recomputes each key and re-runs anything that no
  longer matches, so inheritance cannot make a stale record count. Refuses an invalidated
  source, refuses to overwrite existing trials, is preflight-only, and records every inherited
  trial in `run-manifest.json.inherited_trials`.

- Tests: 4 new in `tests/g02/test_g02_lab.py` (retry-then-succeed, write-never-retried,
  pinned-digests-unchanged, plus the existing failure test no longer sleeping through retries)
  and 4 new in `tests/g03/test_g03_readiness.py` (pass-only inheritance, invalidated-source
  refusal, overwrite refusal, preflight-only). Suites green: g03 31/31, g02 124/124.

- `docs/adr/ADR-0017.md` — removed the dangling citation to an audit section that was never
  written; recorded the 2026-08-12 crash loop, the hardware-class signature, the untested
  CPU-versus-DIMM question, and the nine-day stability record; added the bootstrap-bound and
  host-disappearance consequences.
- `docs/adr/INDEX.yaml` — added the missing ADR-0017 prose-log line.
- `docs/runbooks/G03_BASELINE_READINESS.md` — corrected the precondition that named a
  `PROJECT_STATE.yaml` SUT field which does not exist and which the schema forbids; documented
  the real two-source SUT identity and the mid-run edit hazard. (This file is itself a hashed
  input, so it was edited **before** r4 launched, not during.)
- `docs/governance/LEGACY_GATE_RECORDS.md` — recorded that `governance/gates/G03.yaml`'s
  deletion is intended Governance v2 behavior and must not be recreated.
- `.gitignore` — `newinfo-*/` (host credentials) and `*.stackdump` were untracked but
  **not ignored**; now ignored. Removed a stray `grep.exe.stackdump`.

## Known non-regression — do not "fix"

`run_repository_audit` fails with `required executable not found: pnpm`, and
`tests/audit/test_audit.py::test_repository_audit_generates_valid_cyclonedx` fails for the same
reason. Do not install pnpm to make these pass.

## 8. `core_e2e` penalises live arms for an evidence convention the prompt never states (open)

Found mid-r8 by scoring completed live trials with `score_result_v3` (the same function
`aggregate_reference_v3` calls, verified at `g03_readiness.py:2575`). Recorded here rather than
fixed: the remedy touches `build_baseline_prompt_v3` in `g03_readiness.py`, a hashed input.

### Measured on r8's live trials (FINAL — all three arms complete at n=96, 288/288)

| arm | n | `core_e2e` | label correct | `core_e2e` if `trace_activity` were also cited |
| --- | --- | --- | --- | --- |
| `naive_react` | 96 | **0.1667** | 0.9688 | **0.9688** |
| `no_rag` | 96 | **0.1458** | 0.9479 | **0.9479** |
| `naive_react_single` | 96 | **0.1250** | 0.9583 | **0.9583** |
| `deterministic` | 32 | 0.8125 | — | n/a (see asymmetry below) |

`trace_activity` cited / required, final: `naive_react` 16/96, `no_rag` 18/96,
`naive_react_single` 13/96. All three live arms omit the universal required kind ~83% of the time;
label accuracy is 0.948-0.969 across all three.

Failure classes over 74 trials: `missing_required_evidence` 57 (77%), clean 14 (19%),
`distractor_evidence` 3 (4%). Wrong label only 3/74. `root_cause_top3` 0.9595,
`evidence_precision` 0.9595 — high precision, low recall.

Evidence citation by kind (required vs cited vs missed):

| kind | required | cited | missed |
| --- | --- | --- | --- |
| `trace_activity` | 97 | 16 | **81** |
| `trace_errors` | 48 | 51 | 0 |
| `queue_window` | 25 | 25 | 0 |
| `cpu_window` | 12 | 12 | 0 |
| `memory_window` | 12 | 9 | 3 |

Every kind but one is cited essentially perfectly. `REQUIRED_KINDS`
(`g03_readiness.py:200`) pairs `trace_activity` with a label-specific kind for **all six** labels,
so it is the universal second required kind — and it is the one the agent almost never cites.
`|required_evidence|` is exactly 2 in all 32 cases; the agent cited 1 ID in 64 of 78 trials.

### Why this is a contract defect, not a difficulty measurement

- The prompt (`build_baseline_prompt_v3`) says evidence "must contain only packet IDs that
  **directly support** the diagnosis" and never says the set must be **complete**. Its only
  concrete shape example is `"evidence_refs":["<supporting evidence ID>"]` — singular, which
  teaches exactly the single-citation behaviour observed.
- The schema permits it: `evidence` and `evidence_refs` both carry `minItems: 1`.
- The 4-turn recheck prompt ("Recheck the same packet and prior structured diagnosis") adds no
  evidence guidance either, so no number of turns can surface the requirement. Confirmed as the
  ablation arm completed: `naive_react` 0.1667 vs `naive_react_single` 0.1250, both final at n=96.
  The multi-turn arm is nominally ahead by 0.0417 (4 trials out of 96), which is small against
  binomial noise at this rate and, more to the point, is a gap between two floored values.
  (Interim reads of this queue put the ablation at 0.0909 at n=22 and 0.1571 at n=70; both are
  superseded by the n=96 figure. The argument is unchanged: turns cannot recover an unstated
  requirement.)
- The turn telemetry shows *why* the extra turns are inert: all 96 `naive_react` trials ended with
  `terminal_reason = stable_diagnosis`, 95 of them after exactly 2 drafts whose digests were
  identical. The recheck turn makes the model restate its answer verbatim, not revise it — as
  expected, since the recheck prompt supplies no evidence-completeness criterion to revise against.
  So the multi-turn arm cannot climb out of this by construction, and `max_turns = 4` is never
  reached.
- **The asymmetry that makes the comparison unsound:** `deterministic_baseline_v3` builds its
  evidence list as `sorted(evidence_id_v3(case_id, kind) for kind in REQUIRED_KINDS[root])`. It
  receives the required set **by construction** and never has to infer it. Live arms must guess an
  unstated convention; the deterministic arm is handed the answer key for that conjunct.
- Citing `trace_activity` is risk-free by construction: required for all 6 labels, never in any
  case's `distractor_kinds`, and present with data in 32/32 cases. So this is not a
  precision/recall trade the agent is navigating — it is a rule it was never told.

The rubric itself is defensible: an SRE who names the smoking gun without localising the failing
service has given an incomplete diagnosis. What is not defensible is scoring against that rubric
while the prompt withholds it and the comparison arm is exempt from inferring it. **The fix is to
state the completeness requirement in the prompt, not to relax the scorer.**

### Consequence for the AMD-0007 hard conditions — do not bank these

- Condition 3 (paired deterministic-vs-live difference excludes zero) would be satisfied
  **trivially and for the wrong reason**: 0.8125 vs ~0.17 is a wide gap that is substantially this
  evidence-contract artifact, not a reasoning difference. Before r8 I flagged the opposite risk —
  that a stronger deterministic arm makes this condition *harder*. That was wrong: the artifact
  makes it far easier, which is worse, because it manufactures the significance the gate is
  supposed to test for.
- The `no_rag < naive_react` acceptance criterion becomes a comparison between two
  artifact-compressed numbers. `no_rag` shares the same prompt builder (only the `mode` string
  differs), so it is affected identically. An ordering that emerges between two near-floor values
  is not evidence about retrieval.
- Condition 1 (`best_baseline <= 0.90`) still passes, but because the live arms are floored rather
  than because the dataset is appropriately hard.

Honest limit: the counterfactual column is a **recomputation**, not a measurement. It shows what
the existing answers would have scored had the required `trace_activity` ID been added to the
cited set; it does not prove an agent told to cite completely would keep its 0.96 label accuracy.
Only a re-run with a corrected prompt can establish that.

### Remedy when the run boundary allows it

1. In `build_baseline_prompt_v3`, state that `evidence` must cite **every** packet observation
   supporting the diagnosis, including the trace evidence localising the failing service, and make
   the shape example carry two IDs so it stops teaching single citation.
2. Do **not** change `REQUIRED_KINDS`, `score_result_v3`, or the `minItems` bounds — the rubric
   stays as it is.
3. Consider whether `deterministic_baseline_v3` receiving `REQUIRED_KINDS` directly should be
   recorded as a known asymmetry in AMD-0007, since it cannot be removed without giving the
   deterministic arm an inference task it was never meant to have.
4. Re-run the live reference. The 32 scenario packets and `dataset_digest` are untouched by all of
   this, so trials stay inheritable for the preflight; the live arms must be re-measured.

### Candidate wording, already sized against the token bound

The four-turn bound counts `system_bytes` once per request, so a longer system prompt costs roughly
4x its own length. r8's `max` was `56394` against `FOUR_TURN_INPUT_LIMIT = 58982`, leaving only
`2588` — about **647 bytes** of added system prompt. The remedy must fit that, which rules out a
verbose instruction.

Wording that fits (+346 bytes), inserted before `"Do not add keys."`:

> evidence must be COMPLETE as well as correct: cite every observation ID that supports the
> diagnosis, including the trace observation that localises the failing service, not only the single
> most striking signal. A diagnosis naming the right cause with an incomplete evidence set is scored
> as a failure. Most incidents require more than one observation ID.

plus changing the shape example from `"evidence_refs":["<supporting evidence ID>"]` to
`"evidence_refs":["<ID>","<ID>",...]` so it stops teaching single citation.

Measured with that prompt patched in memory over r8's own 32 packets (`token_preflight_v3`,
read-only, nothing written): `status pass`, `max 57778` (limit `58982`), `p95 56494`,
`headroom_at_max 7758` (required `6554`), `blocked_case_ids []`. So the fix is affordable without
touching any token constant.

Two deliberate choices in that wording. It does **not** name `trace_activity` or any other kind
explicitly — naming the required kinds in the prompt would hand the agent the same answer key
`deterministic_baseline_v3` gets and destroy the inference task. And it states the scoring
consequence, because the rubric is legitimately part of the task specification; what was wrong was
leaving it unstated, not having it.

## 9. r8 returned `readiness_status: ready` with zero blockers — and it should not be banked (open)

r8 completed 288/288 live trials (2.69 CNY, zero infrastructure failures, all three arms 96/96
`pass`) and the gate returned:

```
readiness_status   ready
blocked_reason     None
readiness_blockers []
```

Every AMD-0007 hard condition is satisfied on its own terms:

| condition | result | verdict |
| --- | --- | --- |
| 1. `best_baseline <= 0.90` | `deterministic` 0.8125 | pass |
| 2. six groups complete, presence Top-1 `8/32`, Top-3 `20/32` | pass | pass |
| 3. paired deterministic-vs-live excludes zero | `no_rag - det` `-0.6667` CI `[-0.8125, -0.5104]`; `naive_react - det` `-0.6458` CI `[-0.8021, -0.4792]` | pass |
| 4. non-zero CI widths, complete trial counts, no arm-wide failure | widths 0.208-0.281; 32/96/96 | pass |
| 5. three registered point estimates not exactly equal | 0.8125 / 0.1667 / 0.1458 | pass |

Identity and integrity are clean: `dataset_digest` `8f5a628a...`, `relevant_source_digest`
`702f0ebb...` (matches tree), `metric_definition_digest` `fc6d001b...`, protected assets
byte-identical at both ends (`docs_audit` 21 / `652a2173...`, `g02_frozen` 327 / `d77f4f41...`),
all 32 preflight trials inherited from r5 with `not_inherited: []`.

**The verdict is mechanically correct and substantively unsound.** Condition 3 — the one that
establishes the instrument can tell arms apart — is carried almost entirely by finding 8. The
deterministic arm receives `REQUIRED_KINDS` by construction; the three live arms omit the universal
required kind `trace_activity` in ~83% of trials (16/96, 18/96, 13/96) because no prompt ever asked
for completeness. Their label accuracy is 0.948-0.969. So the `-0.65` paired gap is mostly an
evidence-contract asymmetry, not a reasoning difference, and condition 3 is satisfied by the defect
it was written to detect.

What the run does legitimately establish, and what it does not:

- **Legitimate:** leakage stays eliminated (Top-1 exactly `8/32`, Top-3 `20/32`); the harness is
  reliable (288/288, zero infra failures, zero fallback routes); the deterministic estimator works
  on a complete 32-case dataset; costs are trivial (2.69 CNY).
- **Not established:** that live arms are weak at *diagnosis*. They are weak at an unstated citation
  convention while being 95-97% correct on root cause.
- **Not established:** the `no_rag < naive_react` acceptance ordering. Point estimates do order that
  way (0.1458 < 0.1667), but `naive_react_minus_no_rag` is `+0.0208` CI `[-0.0104, +0.0625]`, which
  **includes zero**. During the run `no_rag` crossed from below to above `naive_react` inside six
  trials. The ordering is observational only — `baseline_order.observational_only` is `true` — and
  is not separated. The multi-turn delta `+0.0417` CI `[+0.0000, +0.0938]` also touches zero at the
  lower bound.

Two independent problems, then: an evidence-contract artifact inflating the deterministic-vs-live
gap, and insufficient power to separate the live arms from each other (per-arm CI widths 0.21-0.23
against inter-arm gaps of 0.02-0.04).

**Recommendation: do not promote r8 to G03 gate evidence.** Not because any check failed — none
did — but because the one condition proving the instrument discriminates is satisfied by an artifact,
and the acceptance ordering it is meant to support is not separated. Banking `ready` here would
close G03 on a measurement that does not mean what the gate says it means.

Sequence to fix, in order:

1. Apply the finding-8 prompt correction (wording already sized: +346 bytes, `token_preflight_v3`
   `pass`, `max 57778` / limit `58982`, headroom `7758` / required `6554`).
2. Re-run preflight (minutes — inherit r8's 32 trials; `dataset_digest` and both checkpoint digests
   are untouched by a prompt change, but confirm before relying on it).
3. Re-measure all three live arms. At ~2.7 CNY per 288-trial round, power is cheap: if the live arms
   land near each other again, raise `repetitions` rather than reading an unseparated ordering.
4. Only then decide whether `no_rag < naive_react` holds with a CI that excludes zero.

Do not, per the runbook and AMD-0007: cap the target, exclude `deterministic` from `best_baseline`
to widen a gap, relax `score_result_v3`, or reinterpret the ordering as separated because the point
estimates happen to order correctly.

r8 itself stays exactly as recorded — it is a sound, complete, honestly-produced run whose figures
should be cited when the corrected round is compared against it. Nothing about it needs
invalidating; it is the interpretation that must not be overstated.

## 10. Items 8 and 9 are closed by r9 — and a new blocker replaces them (2026-09-05)

**Item 8 (evidence-contract defect): resolved and verified.** The disclosure landed in
`build_baseline_prompt_v3`. `trace_activity` citation moved from 16/96, 18/96, 13/96 to
**96/96, 96/96, 93/96**. `missing_required_evidence` dropped from 77% of scored failures to three
trials, all in the unregistered single-turn arm.

**Item 9 (r8 false pass): resolved.** r8's `ready` was carried by that artifact. After disclosure the
gate returns `blocked` with `["best_baseline_above_0_90",
"deterministic_live_significance_not_established"]`. AMD-0007 condition 3, which r8 passed at
`-0.6458` CI `[-0.802, -0.479]`, now fails honestly: all four paired differences straddle zero. The
sign flipped too — all three live arms now score above `deterministic` (0.8125), which is last.

| arm | n | `core_e2e` | 95% CI | `evidence_precision` | failures |
|---|---:|---:|---|---:|---|
| `naive_react` | 96 | 0.9167 | [0.813, 0.990] | 0.9653 | `distractor_evidence` 8 |
| `naive_react_single` | 96 | 0.8854 | [0.781, 0.969] | 0.9601 | `distractor_evidence` 8, `missing_required_evidence` 3 |
| `no_rag` | 96 | 0.8750 | [0.771, 0.958] | 0.9479 | `distractor_evidence` 12 |
| `deterministic` | 32 | 0.8125 | [0.656, 0.938] | 0.8125 | `invalid_label` 6 |

**My pre-registered prediction was falsified; recorded rather than reinterpreted.** AMD-0007
predicted 0.9688 / 0.9479 / 0.9583 and `blocked_reason: dataset_too_easy`. Measured: 0.9167 / 0.8750 /
0.8854 — all **below** the recomputation — and `unclassified`. The cause is the caveat the amendment
itself flagged: mandating complete citation raises distractor risk, and a distractor is a hard
failure. `distractor_evidence` is now the dominant failure class (8/12/8) against 3/74 in r8.

### New blocker (open): the `core_e2e` target is infeasible

`best_baseline` = `naive_react` 0.9167 makes the global floor `max(0.70, best + 0.10)` demand
`core_e2e >= 1.0167` — no solution on the unit interval. The `+0.05` comparison (0.9667) is still
feasible with 0.033 of room. A baseline that reads only a pre-assembled packet and never inspects a
live system reaches 0.9167: this is task saturation.

Prohibited, per the runbook: capping the target, excluding `naive_react`, lowering the `+0.10` floor.
Remedies must change the task — text-blinded packet variants, agent-collected evidence, an open label
set, redesigned distractors. This is a scope decision for the user, not a repair to apply unprompted.

### Recorded, deliberately not fixed: a labelling blind spot

`blocked_reason` reached `unclassified` because the chain tests `dataset_too_easy` on
`no_rag > 0.90` (measured 0.8750) while the arm crossing 0.90 is `naive_react` (0.9167). It affects
only the readability of the diagnosis, never whether the gate admits. Adjusting a predicate so a
label reads better is the class of move this correction exists to prevent.
