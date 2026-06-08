# Hugging Face Gold-Proof Dataset Notes

Checked on 2026-06-08.

## Best V8 Candidate

### `iiis-lean/lean-math-formal-corpus`

- Rows: 2,877
- Useful fields:
  - `nl_problem`
  - `nl_proof`
  - `fl_theorem`
  - `fl_proof`
  - `lean_header`
  - `lean_prefix`
  - `compile_success`
- Observed non-empty counts:
  - `fl_proof`: 616 / 2,877
  - `nl_proof`: 1,013 / 2,877
- V8 config:
  - `configs/benchmarks/lean_math_formal_corpus_goldproof_hf.yaml`

This is the most directly usable source for LAAJ proof-path alignment because it
contains both formal theorem text and gold formal proof bodies for a filtered
subset.

## MiniF2F-Like Datasets

### `brando/minif2f-lean4`

- Splits: `validation`, `test`
- Fields:
  - `formal_statement`
  - `header`
  - `nl_statement`
  - `nl_proof`
- Has gold natural proof, but no gold formal proof.
- Already used by:
  - `configs/benchmarks/minif2f_hf_test.yaml`
  - `configs/benchmarks/minif2f_hf_validation.yaml`

### `AI-MO/minif2f_test`

- Rows: 244
- Fields:
  - `name`
  - `informal_prefix`
  - `formal_statement`
- No gold proof fields observed.

### `Tonic/MiniF2F`

- Rows: 488
- Fields:
  - `formal_statement`
  - `goal`
  - `header`
  - `informal_prefix`
- No gold proof fields observed.

### `CoderBak/minif2f`

- Rows: 488
- Fields:
  - `formal_statement`
  - `natural_language_statement`
- No gold proof fields observed.

### `purewhite42/minif2f_solving`

- Rows: 375
- Fields:
  - `informal_problem`
  - `informal_solution`
  - `formal_answer`
  - `formal_answer_type`
- Useful for proof-path judging or answer-expression analysis, but not directly
  shaped as a Lean theorem-proving benchmark row.

## PutnamBench

### `ChristianZ97/PutnamBench-lean4`

- Rows: 672
- Fields:
  - `problem_name`
  - `formal_statement`
  - `informal_statement`
  - `informal_solution`
  - `tags`
  - `split`
- Has gold natural solution, but no gold formal proof field observed.

### `brando/putnam_bench_informal`

- Dataset access returned HTTP 403 during this check.

## Other Proof Corpora

### `iiis-lean/NuminaMath-LEAN-Sol`

- Rows: 81,311
- Fields:
  - `problem`
  - `solution`
  - `formal_statement`
  - `formal_proof`
  - `statement_source`
  - `proof_source`
- Strong gold formal proof source, but it is more of a solution corpus than a
  miniF2F/Putnam-style benchmark. It may need a dedicated V8 adapter because
  some `formal_statement` values include imports and auxiliary lemma stubs.

### `l3lab/ntp-mathlib-instruct-context-fullproof`

- Splits: `train`, `dev`, `test`
- Fields observed:
  - `task`
  - `prompt`
  - `prompt_name`
  - `completion`
  - `metadata`
- Large proof-instruction corpus. Useful for training/retrieval, less direct as
  a clean benchmark with natural problem + gold theorem + gold proof fields.

### `m-a-p/OProofs`

- Large Lean theorem-proof corpus.
- Useful as a proof memory or training corpus, but too large for quick
  benchmark exploration and not miniF2F/Putnam-specific.

### `nvidia/Nemotron-Math-Proofs-v1`

- Very large dataset, around 29.5GB for the Lean split observed during loading.
- Excluded from this quick benchmark-candidate pass due to size.
