# Red-team fixture data sources

Fixtures in this tree are derived from permissively-licensed public
datasets and are included in the MIT release with attribution.

## `pubtabnet/`

- **Dataset:** PubTabNet — a large-scale corpus of tables extracted from
  PubMed Central scientific articles (IBM Research, hosted via
  `apoidea/pubtabnet-html` on Hugging Face).
- **URL:** https://huggingface.co/datasets/apoidea/pubtabnet-html
- **License:** CDLA-Permissive-1.0 — compatible with MIT redistribution.
- **How derived:** each `.md` file is the `<table>` HTML for a single
  PubTabNet entry (stripped of the surrounding `<html>`/`<head>`
  wrappers). Each `.oracle.json` file lists expected `(row_path,
  col_path, value)` triples computed independently from the HTML
  structure (merge-aware grid walk), plus a `source_tokens` set of
  every cell text string in the source — used to detect fabricated
  tokens in parser output.

Fixture generator: `scripts/build_pubtabnet_fixtures.py`. Oracle
generation does NOT call table2rules (otherwise the test would be
circular); it uses a standalone BeautifulSoup-based walker.
