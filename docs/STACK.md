# Stack

## Used

| Tool | Why |
|---|---|
| Python >= 3.10 | Widest supported range that still allows modern typing syntax. |
| uv | Fast, reproducible environments and builds on Windows and Linux. |
| hatchling | Simple, standards-based build backend; no setup.py. |
| ruff | Lint and format in one fast tool. |
| mypy (strict) | Catches type errors before release; the package ships `py.typed`. |
| pytest + pytest-cov | De facto standard test runner with branch coverage. |
| gitleaks | Secret scanning locally and in CI. |
| uv + the local gate commands | The same four commands run locally and in any CI, so there is no separate wrapper to maintain. |

## Discarded

| Tool | Why not |
|---|---|
| Poetry | Slower, and uv covers the same needs with standard dependency groups. |
| black + isort + flake8 | Replaced by ruff: one tool instead of three. |
| tox / nox | The OS matrix lives in CI; locally the four `uv run` commands are enough. |
| Shell scripts for gates | Not portable to Windows; the gates are plain tool commands. |
