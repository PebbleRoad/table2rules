# Test layout

table2rules has **three test layers**, each answering a different question
about the parser. All three matter. Removing any one leaves a blind spot.

## Layer 1 — Regression (golds)

**File:** [test_regression_golds.py](test_regression_golds.py)
**Question:** "Does the parser produce *exactly* the known-good output for
these hand-authored cases?"

- Fixtures: `tests/fixtures/<class>/*.md`, organized by semantic class
  (see "Fixture taxonomy" below)
- Gold outputs committed under `benchmarks/gold/<format>/fixtures/<class>/`
- Assertion: **byte-for-byte equality** with the gold file
- Strictest layer — catches any output drift at all
- Update golds by running `python scripts/benchmark.py --update-gold`

Add a fixture here when:
- You want to pin down exact output for a specific edge case
- You're testing a hand-crafted adversarial pattern
- You're filling a coverage gap in one of the taxonomy classes

### Fixture taxonomy

Fixtures are filed under `tests/fixtures/<class>/` using the web-table
classification from **Crestan & Pantel, "Web-scale Table Census and
Classification" (WSDM 2011)**. Citing an external taxonomy keeps us honest
about what "we handle tables" means — reviewers can check coverage against
a published schema rather than an invented one.

Genuine data tables:
- **`relational/`** — rows are records, columns are attributes, clear
  header row. The parser's happy path.
- **`matrix/`** — 2D indexed by (row labels × column labels). Nested
  headers, rowgroup/colgroup scopes, rowspan/colspan spine.
- **`attribute-value/`** — two-column (label, value) describing a single
  entity. Infobox pattern.
- **`listing/`** — list of same-type entities with loose or absent
  column headers. Receipts, directories.
- **`form/`** — labels + input fields. The parser must not invent data
  values where the source has none.
- **`enumeration/`** — visually a multi-column list (reflowed). Distinct
  from listing because columns aren't attributes; they're reading order.

Non-genuine (layout) tables — the parser should recognize these and fall
back to flat/passthrough rather than fabricate rules:
- **`navigational/`** — site menus, link grids.
- **`formatting/`** — pure visual layout (image-left text-right, etc.).

Meta (not a Crestan & Pantel class):
- **`multi-table/`** — HTML containing multiple top-level tables, or a
  table nested inside another table's cell. Orthogonal to semantic class;
  exercises the cross-table boundary rather than any one table's type.

### Structural invariants enforced by the pipeline

Three universal rules govern whether a table emits rules-format output.
Violating any of them forces flat fallback — never partial rules.

1. **Row-0 promotion requires structural contrast.** Converting a row
   of `<td>`s into a header row needs at least one subsequent multi-cell
   row with at least one empty cell. Without that contrast there is no
   structural evidence that row 0 plays a different role from the rows
   below it. Enforced in `simple_repair.Fix 4` and `grid_parser` step 3.

2. **Rules mode requires every rule to carry at least one header.** A
   rule with zero headers is indistinguishable from flat text — the
   rules format implies a header relationship that doesn't exist
   otherwise. Enforced in `quality_gate.low_header_attachment` (fires
   universally at `header_ratio < 1.0`, not on a threshold).

3. **Section-title rows are not header rows.** A `<tr>` whose sole cell
   is a `<th>` with colspan covering the grid width is a section label,
   not a header or data row. First-row instances are moved to
   `<caption>`; mid-table instances are decomposed. Enforced in
   `simple_repair.Fix 1` (first row) and `Fix 1b` (mid-table).

These rules are all deterministic properties of the markup — cell type,
span values, empty-vs-non-empty, row count. No content analysis, no
percentage thresholds.

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
| **Fixture count (current)** | 57 | 200 | 200 × ~10 operators = ~2000 |

Together they give: "we don't drift, we're correct when we can be, and
we never fabricate when we can't."

## Public API guards

Two additional test files guard the public surface rather than the parser's
input/output behaviour. They catch contract breakage that the three input
layers wouldn't:

- **[test_public_api.py](test_public_api.py)** — `LogicRule` is frozen and
  hashable; `process_tables_with_stats` returns the documented
  `RenderReport` / `TableReport` shape; every `render_mode` value is
  reachable; `TableTooLargeError` triggers at the documented span cap;
  every reason code emitted against the fixture corpus appears in
  `REASONS`. A new reason string added to the gate without a matching
  description in `report.REASONS` fails this suite.

- **[test_determinism.py](test_determinism.py)** — runs every regression
  fixture twice through both public entry points, asserts byte-identical
  output both times. Cheap insurance against accidental ordering
  dependencies (set iteration, dict traversal, locale-sensitive sorting).

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
