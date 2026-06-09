---
language:
- en
license: other
size_categories:
- n<1K
task_categories:
- question-answering
- text-generation
pretty_name: Tokyo University Mathematics Problems 2024-2026 Revised Integer QA
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
---

# Tokyo University Mathematics Problems 2024-2026 Revised Integer QA

This dataset contains English LaTeX-style mathematics question-answer pairs derived from revised Tokyo University entrance-exam-style mathematics problems for 2024-2026. The problems have been modified so that each final answer is a single integer.

## Dataset Structure

Each row has the following fields:

- `no`: problem number
- `ID`: problem identifier
- `Question`: English problem statement written with LaTeX math
- `Answer`: final integer answer
- `Solution`: step-by-step solution
- `Difficulty`: difficulty label

## Files

- `data/train.jsonl`: recommended file for Hugging Face Dataset Viewer and `load_dataset`
- `data/train.json`: same data as a JSON array
- `data/train.csv`: CSV version
- `tokyo_university_2024_2026_math_english_integer_final_schema.tex`: LaTeX source version

## Loading

```python
from datasets import load_dataset

dataset = load_dataset("YOUR_USERNAME/YOUR_DATASET_NAME")
print(dataset["train"][0])
```

Or locally:

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="data/train.jsonl")
```

## Notes

The questions were revised to avoid final answers that are irrational numbers, parameterized expressions, ranges, proofs, drawings, graphs, locus equations, or region descriptions.

## License and Rights

Please verify that you have the right to redistribute the source material and derived translations before making the repository public. If rights are uncertain, keep the dataset private or choose an appropriate restricted/custom license.
