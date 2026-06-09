# Tokyo Private Hugging Face Evaluation

This copy of EntropyMath Eval is configured for the Tokyo math dataset.

## 1. Set Secrets

Copy `.env.example` to `.env` and fill in the values:

```bash
HF_TOKEN=hf_your_private_dataset_read_token
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key
```

You can also log in once with:

```bash
huggingface-cli login
```

If you use `huggingface-cli login`, you may remove `hf_token_env: HF_TOKEN`
from `configs/competitions/tokyo_math_hf_private.yaml`.

## 2. Set The Private Dataset Id

Edit:

```text
configs/competitions/tokyo_math_hf_private.yaml
```

The private Hugging Face dataset id is already set:

```yaml
dataset_path: Co0oC/tokyo_mathEval
```

The runner already recognizes the dataset columns:

- `Question` as the problem text
- `Answer` as the gold answer

## 3. Smoke Test

Run one problem first:

```bash
export HF_HOME="$PWD/.cache/huggingface"
export HF_DATASETS_CACHE="$PWD/.cache/huggingface/datasets"
.venv/bin/python scripts/run.py \
  --dotenv .env \
  --comp tokyo_math_hf_private \
  --model openrouter_gpt_5_4_mini \
  --solver direct \
  --n_repeats 1 \
  --max-problems 1
```

## 4. Full Run

```bash
.venv/bin/python scripts/run.py \
  --dotenv .env \
  --comp tokyo_math_hf_private \
  --model openrouter_gpt_5_4_mini \
  --solver direct \
  --n_repeats 3
```

## 5. Summarize

```bash
.venv/bin/python scripts/summarize_entropymath_results.py \
  --input outputs/tokyo_math_hf_private \
  --output outputs/tokyo_math_hf_private_summary.json
```

## Run Every Model Config

The repository includes many model configs with different provider keys and
local endpoint assumptions. This command tries every YAML in `configs/models`
and continues after individual model failures. The batch script automatically
uses `.cache/huggingface` inside this repo for dataset caching.

```bash
.venv/bin/python scripts/run_tokyo_all_models.py \
  --dotenv .env \
  --solver direct \
  --n-repeats 1
```

Smoke test every model on one problem:

```bash
.venv/bin/python scripts/run_tokyo_all_models.py \
  --dotenv .env \
  --solver direct \
  --n-repeats 1 \
  --max-problems 1
```

Pass@3-style direct evaluation:

```bash
.venv/bin/python scripts/run_tokyo_all_models.py \
  --dotenv .env \
  --solver direct \
  --n-repeats 3
```

Tool-assisted evaluation:

```bash
.venv/bin/python scripts/run_tokyo_all_models.py \
  --dotenv .env \
  --solver tool \
  --n-repeats 3
```

## Local Dataset Fallback

To test without Hugging Face, use the local JSONL config:

```bash
.venv/bin/python scripts/run.py \
  --comp tokyo_math_local \
  --model openrouter_gpt_5_4_mini \
  --api-key-env OPENROUTER_API_KEY \
  --solver direct \
  --n_repeats 1 \
  --max-problems 1
```
