# CodingTheoryLib `agents/evaluation` Analysis

Fetched reference:

- `references/CodingTheoryLib` in the local workspace used for development
- target path: `agents/evaluation`

## What To Reuse

The reference pipeline is a Natural-to-Lean evaluator. Its reusable core for
`math_eval_v8` is:

- `verifier.py`: Lean code extraction, `sorry/admit` rejection, diagnostics
  parsing, and file-based `lake env lean` verification.
- `repl_verifier.py`: warm Lean REPL verification for throughput. This is useful
  later, but file-based verification is simpler and more portable for v8 first.
- `provers.py`: LM Studio/OpenAI-compatible model calls, Lean fenced block
  parsing, shell/proof separation, and repair loops.
- `scoring.py`: pass@k grouping by problem/model/condition.
- `fidelity.py`: lightweight rejection of vacuous theorem statements.

## What Not To Copy Directly

The CodingTheoryLib adapter is tightly coupled to `import CodingTheoryLib`,
retrieval context, graph/RAG modes, and coding-theory statement fidelity. For
miniF2F and PutnamBench this would be the wrong abstraction. v8 should instead
use dataset-configured imports and benchmark rows.

## V8 Design

V8 keeps the v7 outer loop but replaces answer grading:

- v7: problem text -> model -> `\boxed{}` extraction -> string/SymPy grading
- v8: formal theorem row -> model -> Lean code extraction -> Lean verifier

The result schema is centered on:

- `candidate_code`
- `formal_statement`
- `verifier.ok`
- `verifier.complete`
- `verifier.errors`
- `verifier.warnings`
- `pass@k` summary

## LM Studio Models

The initial configs mirror the local v7 LM Studio setup:

- `qwen_coder_30b_lmstudio.yaml`
- `gpt_oss_20b_lmstudio.yaml`

Both point to `http://localhost:1234/v1`, use `api_key: not-needed`, and can be
overridden on the CLI with `--model-id-override`.
