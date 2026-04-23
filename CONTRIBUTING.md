# Contributing to table2rules

Thanks for your interest in contributing. This is a small, narrowly-scoped
library — the bar for changes is "does it make the HTML-table → rules
conversion more correct, safer, or clearer?" Anything broader should be
raised as an issue first.

## Development setup

```bash
git clone https://github.com/pebbleroad/table2rules
cd table2rules
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The full test suite runs in a few seconds. CI runs it on Python 3.9 → 3.13.

## Making changes

- **Keep changes focused.** One behavior change per PR. If you're tempted to
  refactor unrelated code in the same PR, open a separate one.
- **Add a test.** Every behavior change needs a test covering it. Parser
  changes should add a fixture under [tests/](tests/) that demonstrates the
  bug or the new case.
- **Preserve fail-open safety.** This library is designed to degrade
  gracefully on hostile input rather than raise. If your change narrows that
  contract, call it out in the PR description.
- **No new runtime dependencies** without discussion. `beautifulsoup4` is
  the only one and that's deliberate.
- **Update [CHANGELOG.md](CHANGELOG.md)** under an `Unreleased` heading if
  your change affects public behavior.

## Running the full validation layer

```bash
pytest                                            # unit + regression tests
python scripts/measure_token_savings.py           # reproduces README numbers
```

See [docs/validation.md](docs/validation.md) for the oracle + mutation test
model.

## Reporting bugs

Open an issue with:

- A minimal HTML input that reproduces the problem.
- The output you got.
- The output you expected.

For security-sensitive issues, see [SECURITY.md](SECURITY.md) instead.
