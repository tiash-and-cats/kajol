# kajol vs uv: Benchmark Report

## Package Installation

| Package      | Cache |  kajol |     uv |
| ------------ | ----- | -----: | -----: |
| `rich`       | Cold  |  4.96s |  3.33s |
| `matplotlib` | Cold  | 21.40s | 20.50s |
| `rich`       | Warm  |  1.99s |  0.35s |
| `matplotlib` | Warm  |  5.97s |  1.04s |

## Python Installation

| Python version |  kajol |     uv |
| -------------- | -----: | -----: |
| 3.13           | 28.45s | 25.94s |
| 3.14           | 24.98s | 24.07s |
| 3.15.0rc2      | 23.07s | 13.44s |