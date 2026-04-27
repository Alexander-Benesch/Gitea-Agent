# Contributing to S.A.M.U.E.L.

## Setup

```bash
git clone http://192.168.1.60:3001/Alexmistrator/S.A.M.U.E.L.git
cd S.A.M.U.E.L
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development Workflow

1. Create a branch from `main`: `git checkout -b feat/my-feature`
2. Write code + tests
3. Run tests: `python -m pytest`
4. Run linter: `ruff check samuel/ tests/`
5. Create PR — the 14 PR gates will check your code

## Architecture Rules

- **No cross-slice imports** — slices only import from `samuel.core.*`
- **No direct adapter usage in slices** — use Ports (ABCs from `samuel.core.ports`)
- **Tests live with their slice** — `samuel/slices/<name>/tests/test_handler.py`
- **One event per state change** — events are published via the Bus

## Code Style

- Python 3.10+, type hints everywhere
- `ruff` for linting and formatting
- No comments unless the WHY is non-obvious
- Commit messages: `feat|fix|docs|test(scope): description`

## Tests

```bash
# All tests
python -m pytest

# Single slice
python -m pytest samuel/slices/planning/tests/

# Architecture validation
python -m pytest tests/test_architecture_v2.py
```
