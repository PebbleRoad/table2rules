# Benchmarks

This folder tracks deterministic outputs for the markdown tables under `test tables/`.

- `gold/` contains expected outputs (reviewed baseline).
- `current/` contains outputs from the latest benchmark run.

## Usage

From repo root:

```bash
python3 benchmark_tables.py --allow-missing-gold
```

Create or refresh gold outputs:

```bash
python3 benchmark_tables.py --update-gold
```

Compare current outputs against gold with diffs:

```bash
python3 benchmark_tables.py --show-diff
```
