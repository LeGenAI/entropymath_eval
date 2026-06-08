# Math Eval V8

`math_eval_v8` is a Lean-formal benchmark evaluator for miniF2F, PutnamBench,
and similar theorem-proving datasets. It keeps the v7 evaluation shape:

1. load benchmark config
2. call an LM Studio/OpenAI-compatible model
3. save one JSON result per problem/repeat
4. verify outputs with Lean
5. summarize pass@k

The important change from v7 is the grading surface. v7 extracts a boxed
numeric/string answer. v8 extracts Lean code and scores a run only when Lean
accepts a complete proof with no `sorry` or `admit`.

## Basic Usage

```bash
cd math_eval_v8
python3 scripts/run.py \
  --bench configs/benchmarks/minif2f_jsonl.yaml \
  --model configs/models/qwen_coder_30b_lmstudio.yaml \
  --max-problems 5 \
  --n-repeats 1
```

For Lean verification with Mathlib-backed datasets, set `lean_project_path` in
the benchmark config to a Lake project that can run `lake env lean`.

## Current LM Studio Panel

The default two-model panel uses the two prover models exposed by the local
LM Studio server:

- `goedel-prover-v2-8b`
- `bytedance-seed.bfs-prover-v2-7b`

Run both on the Hugging Face miniF2F test split:

```bash
cd math_eval_v8
python3 scripts/run_panel.py \
  --bench configs/benchmarks/minif2f_hf_test.yaml \
  --panel configs/model_panels/lmstudio_two_models.yaml \
  --lean-project-path /path/to/lean/project \
  --max-problems 5 \
  --n-repeats 1
```

If LM Studio exposes a different model id in `/v1/models`, pass it to
`scripts/run.py` with `--model-id-override`.

## Input Row Fields

The loader accepts Hugging Face datasets or local JSONL. Useful fields are:

- `formal_statement`, `theorem`, `lean_statement`, or `statement`
- `informal_statement`, `natural_statement`, or `problem`
- `proof` or `gold_proof` if present
- `id`, `problem_id`, `name`, or `problem_name`

Rows may contain only a formal statement. If the statement has no proof body,
v8 asks the model to return a complete Lean 4 file proving it.
