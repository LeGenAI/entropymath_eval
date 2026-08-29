# Model Metrics

| Model | Pass@1 | Pass@3 | Wall-clock time | Input tokens | Output tokens | Total tokens | Token-reported runs |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-EXAONE | 100.00% | 100.00% | 1h 39m 41s | 14,820 | 698,982 | 713,802 | 90/90 |
| Opus 4.8 | 100.00% | 100.00% | 12m 32s | 24,438 | 59,223 | 83,661 | 90/90 |
| Gemini 3.5 Flash | 100.00% | 100.00% | 18m 32s | 16,941 | 239,536 | 256,477 | 90/90 |
| GPT-5.5 | 100.00% | 100.00% | 16m 27s | 17,340 | 39,044 | 56,384 | 90/90 |
| DeepSeek V4 Pro | 86.67% | 96.67% | 1h 8m 14s | 15,573 | 178,544 | 194,117 | 86/90 |
| Solar Pro 3 | 90.00% | 93.33% | 26m 41s | 21,969 | 237,224 | 259,193 | 90/90 |
| KT Mi:dm 2.0 | 60.00% | 66.67% | 2m 36s | 62,031 | 48,503 | 110,534 | 90/90 |

- Pass@1 and Pass@3 count error/empty-response runs as incorrect.
- Wall-clock time includes rate-limit waits, empty responses, and request overhead.
- Token totals include successful runs where the provider returned token usage.