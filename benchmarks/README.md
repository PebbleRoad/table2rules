# Benchmarks

Tracks deterministic outputs for every test case under `tests/` against a
reviewed baseline. Gold/current outputs are stored per exporter so multiple
output formats can be benchmarked independently.

- `gold/<format>/` — expected outputs (reviewed baseline).
- `current/<format>/` — outputs from the latest benchmark run (gitignored).

## Usage

From repo root:

```bash
python3 scripts/benchmark.py --allow-missing-gold
```

Pick a specific exporter (default is `rules`):

```bash
python3 scripts/benchmark.py --format rules
```

Create or refresh gold outputs for the selected format:

```bash
python3 scripts/benchmark.py --update-gold
```

Compare current outputs against gold with diffs:

```bash
python3 scripts/benchmark.py --show-diff
```
