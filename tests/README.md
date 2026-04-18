# Test layout

table2rules has **three test layers**, each answering a different question
about the parser. All three matter. Removing any one leaves a blind spot.

## Layer 1 — Regression (golds)

**File:** [test_regression_golds.py](test_regression_golds.py)
**Question:** "Does the parser produce *exactly* the known-good output for
these hand-authored cases?"

- Fixtures: `tests/{adversarial,headerless,regression,smoke,structured}/*.md`
- Gold outputs committed under `benchmarks/gold/<format>/`
- Assertion: **byte-for-byte equality** with the gold file
- Strictest layer — catches any output drift at all
- Update golds by running `python scripts/benchmark.py --update-gold`

Add a fixture here when:
- You want to pin down exact output for a specific edge case
- You're testing a hand-crafted adversarial pattern

## Layer 2 — Correctness (oracle)

**File:** [test_correctness_oracle.py](test_correctness_oracle.py)
**Question:** "On *clean real-world tables*, does the parser produce
semantically correct rules — right headers mapped to right values?"

- Fixtures: `tests/realworld/<dataset>/*.md` + `*.oracle.json` pairs
  (currently 200 PubTabNet tables from PubMed Central, CDLA-Permissive-1.0)
- Oracles are computed independently from the source HTML structure
  (standalone BeautifulSoup walker; does NOT call table2rules, so the
  test is not circular)
- Assertion: **side-aware header-token subset match** with value lookup,
  plus source-cell whitelist for any extras the parser includes. Tier
  fallback (FLAT / PASSTHROUGH) is treated as a *skip*, not a failure —
  the contract is "correct rules when we emit rules."

Catches: misattribution (wrong header → value), dropped headers on clean
input, concat/fabrication bugs.

Add a fixture here when:
- You want to stress-test structural parsing against real-world tables
  with a ground-truth oracle

Regenerate the fixtures with:
```
python scripts/build_pubtabnet_fixtures.py
```

See [tests/realworld/DATA_SOURCES.md](realworld/DATA_SOURCES.md) for
attribution and license details.

## Layer 3 — Robustness (mutations)

**File:** [test_robustness_mutations.py](test_robustness_mutations.py)
**Question:** "When fed *corrupted real-world HTML*, does the parser
stay safe — no hallucinated content?"

- Fixtures: the same PubTabNet fixtures as Layer 2, but each is
  mutated on-the-fly by one of ~10 operators that simulate production
  HTML noise: whitespace, HTML entities, `<span>`/`<b>` wrappers around
  cell content, Word-style `<td><b>header</b></td>`, paginated duplicate
  header rows, mismatched close tags, `<br>` inside cells, multi-tbody
  splits, etc.
- Assertion: **relaxed** — every emitted value must be a real source
  cell, and every emitted header token must be a real source cell.
  Headers may be *partially dropped* under stress; that's a degradation,
  not a failure. FLAT / PASSTHROUGH fallbacks are also treated as skips.

Catches: fabrication under stress (invented tokens, concat strings),
values hallucinated from noise.

Add an operator here when:
- You encounter a real-world HTML quirk that we should be robust to

## How the three layers relate

| | Regression | Correctness | Robustness |
|-|-|-|-|
| **Input** | hand-authored | clean real-world | corrupted real-world |
| **Oracle** | exact gold text | per-cell triple from source | per-cell triple (same as Layer 2) |
| **Assertion** | equality | `oracle ⊆ emitted ⊆ source` | `emitted ⊆ source` |
| **Primary failure mode it catches** | output drift | misattribution / drop | fabrication |
| **Fixture count (current)** | 44 | 200 | 200 × ~10 operators = ~2000 |

Together they give: "we don't drift, we're correct when we can be, and
we never fabricate when we can't."

## Future dataset coverage

The Layer-2 / Layer-3 real-world corpus is currently PubMed-only. The
following datasets are MIT-compatible candidates for broadening structural
coverage to other domains — listed in priority order:

- **FinTabNet** (IBM, CDLA-Permissive-1.0, ~112k tables). Financial 10-K
  report tables. Exercises deeply nested row stubs, parenthesized negative
  numbers, footnote markers, multi-year column groups. Available via
  HuggingFace (`apoidea/fintabnet-html` or `katphlab/fintabnet-pubtables-full`).
  Estimated effort: 1 session — the generator pattern from
  [../scripts/build_pubtabnet_fixtures.py](../scripts/build_pubtabnet_fixtures.py)
  ports directly.

- **SynthTabNet** (IBM, CDLA-Permissive-1.0). Synthetic but
  MIT-safe — useful for controlled stress (specific structural knobs:
  header depth, merge density, stub-column count). Good for
  regression-hardening, less for "realism" credibility.

- **SEC EDGAR filings** (U.S. government, public domain). Raw HTML
  straight from filers — the messiest legitimate HTML in the wild: inline
  CSS, `<font>` tags, nested `<div>`s used as layout tables, Word-pasted
  content. Would add a second oracle-free "wild HTML" corpus for the
  robustness layer (parser must not crash or fabricate, but we won't
  oracle-match). Requires a lightweight scraper and manual sampling.

- **SciTSR** (scientific paper tables, MIT-compatible license on
  GitHub). ~15k tables. Overlaps with PubTabNet in domain; adds value
  mainly as a cross-check that we're not over-fit to PubTabNet's
  rendering conventions.

- **TableBank** (ICDAR 2019, Apache 2.0). Diverse web tables scraped
  from arXiv and Word documents — useful for both Layer-2 oracle
  matching and Layer-3 mutation testing of arXiv-style math-heavy tables.

Non-dataset ideas also worth adding:
- **Property-based fuzzing** via Hypothesis on top of the grid builder —
  generates synthetic malformed HTML with invariants ("parser never
  crashes, never emits invented tokens").
- **A small curated "wild HTML" sample** (15–30 tables hand-picked from
  public websites) — no oracle, sanity-only, committed under a clear
  license chain.

Each of these adds a *different* kind of coverage. We do not need all
of them; pick based on what deficiency you need to close.
