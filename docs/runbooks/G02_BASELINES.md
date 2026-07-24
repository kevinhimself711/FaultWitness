# G02 Baseline Runner

I-0019 implements three diagnosis-only baselines over the same canonical observation packet. The
packet contains a problem brief and observations only; `fault_action`, ground-truth references,
locked-test metadata, difficulty, and split are rejected before a baseline runs.

The deterministic workflow performs no model call. `naive_react` and `no_rag` use only Bailian
model `qwen3.7-plus-2026-05-26`; fallback profiles are empty. Naive ReAct is capped at four turns,
six tool calls, 8,000 input tokens, and 1,024 output tokens. No-RAG uses one structured completion,
4,000 input tokens, and 512 output tokens. The frozen price record is 2 CNY/million input tokens and
8 CNY/million output tokens.

Normal execution has no preset orchestration wall-clock kill timeout. That removal does not alter
the 90-second fault-oracle windows, validation N, token ceilings, one internal transient retry,
quality floors, performance measurements, or Gate criteria. DNS/TLS/transport, 429, and 5xx after
the fixed retry become `infra_failed`. Only that trial is resumed. A valid-but-wrong, malformed,
schema-invalid, or budget-exhausted answer is a scored failure and is not rerun.

Every trial is written atomically before the next trial starts. A passing trial is immutable for the
same trial ID. The Gate runner accepts exactly 32 deterministic rows and exactly 192 live trials,
then calculates a 95% percentile bootstrap CI with 2,000 resamples clustered by case ID and seeded
from the dataset digest.

The unified Gate phases execute these matrices directly from the completed candidate-bound
`scenario-matrix` artifact. They do not import operator-produced deterministic or live result JSON.
`baseline-deterministic` executes all 32 packets, `baseline-live` derives 192 trial identities from
the candidate SHA, dataset digest, exact model, baseline, case ID, and repetition, and
`baseline-aggregate` scores the persisted results against sealed evaluator truth. The journal root
is repository-external; a rerun reuses passing trial records and continues only `infra_failed`
records.

Iteration execution is:

```text
uv run python -m faultwitness_dev eval-iteration I-0019 --candidate-sha <full-sha>
```

The command performs only the frozen N=3 deterministic smoke and N=4 non-seed live smoke. It never
runs the Gate N=32/N=192 matrices.
