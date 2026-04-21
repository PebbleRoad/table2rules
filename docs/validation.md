# Validation

How `table2rules` is tested, on what corpora, and what it has *not* been
tested against. If you're evaluating the library for production, this is
the page worth reading in full.

## Smoke coverage

The repo ships hand-authored fixtures that exercise every structural
pattern the parser supports:

| Table type | Structure | Sample output |
|------------|-----------|---------------|
| Key-value | 2 cols, th+td pattern | `Name: John` |
| Invoice | No thead, implicit headers | `Widget \| Qty: 2` |
| SLA report | 2-row thead, colspan | `High \| SLA Met > Yes: 5` |
| Schedule | 3-row thead, body rowspan | `AI \| Day 1 > AM: Keynote` |
| Financial | 3-level headers, rowgroups | `NA > East \| Q1 > Sales > Rev: 100` |
| Benefits | Mixed colspan in body | `Health > Medical \| Level > Junior: $100` |
| Clinical trial | 4-row thead, 3 regions, 9 sites, 12 columns | 100 rules extracted correctly |

See `tests/smoke/`, `tests/structured/`, and `tests/adversarial/` for the
full fixture set.

## Real-world corpus

The parser is stress-tested against an external corpus, not just the
author's handwritten fixtures:

- **200 tables from PubTabNet** — tables extracted from PubMed Central
  scientific articles, CDLA-Permissive-1.0 — with per-cell oracle matching.
  The oracle is computed from the source's own structural annotations,
  independent of this parser, so a failing test means the parser actually
  disagrees with the ground truth (not with itself).
- **~2,000 mutation tests** applying 10 real-world HTML noise patterns on
  top of those 200 tables: `<span>` / `<b>` cell wrappers, Word-style
  `<td><b>Header</b></td>`, paginated duplicate header rows, mismatched
  close tags, NBSP padding, `<br>` inside cells, multi-tbody splits, and
  more.
- **No-fabrication contract:** emitted rules either match the oracle
  exactly, or the parser falls back to flat / passthrough. The library
  never invents content that isn't present in the source.

See [../tests/README.md](../tests/README.md) for the three-layer test
model (regression · correctness · robustness) and
[../tests/realworld/DATA_SOURCES.md](../tests/realworld/DATA_SOURCES.md)
for dataset attribution.

## What has not been tested

Setting honest expectations — these are known coverage gaps, not bugs:

- **Domains outside scientific papers.** The real-world oracle corpus is
  PubMed Central tables. Financial 10-K filings, sports statistics, legal
  schedules, and newswire tables may have structural idioms this test set
  doesn't exercise. See
  [../tests/README.md](../tests/README.md#future-dataset-coverage) for
  planned additions.
- **Browser-only tables.** Tables rendered by JavaScript, reconstructed
  from CSS grids, or pasted as Excel clipboard fragments are out of scope
  — the input contract is HTML markup.
- **Round-trip ambiguity on cells containing ` > `, ` | `, or `: `.**
  These characters are the rule-format separators, so a cell whose own
  text contains them cannot be distinguished from a split path on the
  consumer side. Data is preserved; cosmetic parsing is ambiguous.

## Running the test suite

```bash
pip install -e '.[dev]'
pytest
```

Each test layer has its own file:
[test_regression_golds.py](../tests/test_regression_golds.py),
[test_correctness_oracle.py](../tests/test_correctness_oracle.py),
[test_robustness_mutations.py](../tests/test_robustness_mutations.py),
plus [test_public_api.py](../tests/test_public_api.py) (contract tests for
the public surface) and [test_determinism.py](../tests/test_determinism.py)
(byte-identical reproducibility check).

## Maintenance scripts

`scripts/benchmark.py` is a richer harness for diffing and refreshing the
gold corpus:

```bash
# Run and diff current output vs gold
python3 scripts/benchmark.py --show-diff

# Refresh expected outputs after an intentional format change
python3 scripts/benchmark.py --update-gold

# Pick an exporter (default: rules)
python3 scripts/benchmark.py --format rules
```

`scripts/fuzz.py` generates randomized hostile inputs for the parser.
