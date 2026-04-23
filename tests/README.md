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

Six universal rules govern whether a table emits rules-format output.
Violating any of them forces flat fallback — never partial rules.

1. **Header-block boundary is geometrically determined.** The header
   block is the maximal leading prefix of rows that ends at the first
   *data row*, where a data row has (a) col 0 non-empty, (b) ≥ 2
   non-empty logical cells, (c) every logical position filled by an
   origin cell at this row (no rowspan copy from above), and (d) all
   origin cells at `rowspan == colspan == 1`. Rows in the prefix may
   carry empty cells only at *stub-column* positions — columns that
   are empty in every header row AND non-empty in a strict majority
   of non-divider body rows. The strict-majority count lets the rule
   accept tables with a trailing unlabeled summary row (e.g., a
   financial totals line where the row-label cell is intentionally
   blank) while still refusing to promote a sparsely-filled data
   column. Enforced in `simple_repair.detect_header_block`, used by
   Fix 4 and `grid_parser` Step 3.

2. **Row-group dividers propagate as ancestors within their extent.**
   A body row whose single non-empty logical cell sits in a stub
   column is a row-group header (the FinTabNet "2014" year-label
   pattern). It is promoted to `<th scope="rowgroup">` and its text
   prepends to `row_path` for subsequent body cells — but only within
   its *extent*. For `rowspan > 1`, the extent is the rowspan range;
   for `rowspan == 1` (divider-style), it runs until the next
   rowgroup origin in the same column. The `rowspan == 1` case is
   structurally distinct from an explicit-rowspan peer header (North
   / South with `rowspan="2"` each) — both can coexist and the extent
   rule keeps them from nesting incorrectly. Enforced in
   `simple_repair.Fix 4` (promotion) and
   `maze_pathfinder.find_headers_for_cell` (extent check).

3. **Rules mode requires every rule to carry at least one header.** A
   rule with zero headers is indistinguishable from flat text — the
   rules format implies a header relationship that doesn't exist
   otherwise. Enforced in `quality_gate.low_header_attachment` (fires
   universally at `header_ratio < 1.0`, not on a threshold).

4. **Section-title rows are not header rows.** A `<tr>` whose sole cell
   is a `<th>` with colspan covering the grid width is a section label,
   not a header or data row. First-row instances are moved to
   `<caption>`; mid-table instances are decomposed. Enforced in
   `simple_repair.Fix 1` (first row) and `Fix 1b` (mid-table).

5. **Column-header detection ignores row-scoped `<th>`.** A
   `<th scope="row">` labels a row, not a column, so it cannot make a
   body row qualify as the primary column-header row — otherwise a
   single summary row like "Total" (promoted by Fix 5) could be
   mistaken for the table header. Enforced in `grid_parser` Step 1.

6. **Unlabeled descriptor columns promote via alphabetic majority.**
   When a body column has no thead text but its non-empty body cells
   are *strictly majority textual* — any Unicode letter counts, via
   `str.isalpha()` — it is treated as a row-stub (dimensional) column,
   provided it sits at the left edge or is contiguous with another
   promoted descriptor column. This is the one principled exception
   to "no content analysis": the alphabetic-vs-numeric distinction
   is universal across writing systems (letters label, digits measure),
   and counts — not ratios — make the rule deterministic. Enforced in
   `grid_parser` Phase 3.5 Signal B.

Rules 1–5 are deterministic properties of the markup only — cell type,
span values, empty-vs-non-empty, row count, per-column fill patterns.
Rule 6 reads cell text solely to ask "does this character classify as
a letter in any writing system?" — a Unicode-level structural question,
not semantic content. All numeric comparisons are integer counts
(row totals, "more than", strict majority); no percentage thresholds.

## Layer 2 — Correctness (oracle)

**File:** [test_correctness_oracle.py](test_correctness_oracle.py)
**Question:** "On *clean real-world tables*, does the parser produce
semantically correct rules — right headers mapped to right values?"

- Fixtures: `tests/realworld/<dataset>/*.md` + `*.oracle.json` pairs
  (currently 200 PubTabNet tables from PubMed Central and 200 FinTabNet
  tables from IBM 10-K filings, both CDLA-Permissive-1.0)
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
python scripts/build_fintabnet_fixtures.py
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
| **Fixture count (current)** | 57 | 400 (200 PubTabNet + 200 FinTabNet) | 400 × ~10 operators = ~4000 |

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

The Layer-2 / Layer-3 real-world corpus now spans PubMed scientific
tables (PubTabNet, 200 fixtures) and IBM 10-K financial tables
(FinTabNet, 200 fixtures). The following datasets are MIT-compatible
candidates for broadening structural coverage further — listed in
priority order:

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
