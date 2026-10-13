| run | n_pairs | differ_d1 | differ_d10 | differ_d11 | differ_d12 | differ_d20 | differ_d30 | same_d10 | differ_d11_given_same_d10 |
|---|---|---|---|---|---|---|---|---|---|
| R-daily | 95 | 32 | 38 | 40 | 39 | 38 | 38 | 57 | 14 |
| R-clock | 95 | 32 | 37 | 39 | 39 | 38 | 40 | 58 | 15 |
| L-clock (mock) | 95 | 48 | 45 | 45 | 44 | 48 | 45 | 50 | 19 |
| L-daily (mock) | 95 | 48 | 43 | 39 | 41 | 48 | 41 | 52 | 19 |
| R-clock (traits off) | 95 | 0 | 12 | 6 | 6 | 6 | 6 | 83 | 2 |
| L-clock (mock) (traits off) | 95 | 0 | 12 | 21 | 21 | 22 | 22 | 83 | 19 |

Twins share Layer A. Rule noise uses common random numbers for twins and MockLLM is seeded by the prompt, so with traits off (identical A and B) a difference comes from history only. MockLLM is a pipeline check, not an LLM.
