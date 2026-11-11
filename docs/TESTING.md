# Testing

## Running

```sh
uv run pytest --cov=docs_link_check   # tests with coverage report
uv run ruff check .                   # lint
uv run ruff format --check .          # formatting
uv run mypy                           # types
```

## Policy

- Branch coverage of `src/docs_link_check` must stay at or above 80 %; the gate fails below it.
- Tests exercise the public API (`import docs_link_check`) and assert every observable effect:
  return values, raised exceptions and their messages.
- Each bug fix starts with a failing test that reproduces it.
- Tests are deterministic: no network, no wall clock, no dependence on test order.

## Tiers

- Local tier (every gate run, coverage measured here): unit and property tests, plus conformance on small
  fixtures kept in the repository.
- CI tier: conformance that needs an external tool or a download. Mark them `@pytest.mark.conformance`; they are
  deselected locally (unless `FABRICA_CI=1`) and run in full when `FABRICA_CI=1` is set. Tagged tests skip cleanly
  when their tool is missing.

## Layout

`tests/test_<module>.py` mirrors each public module. Shared fixtures go in `tests/conftest.py`.
