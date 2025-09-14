# table2rules

A universal system that transforms any HTML table into queryable IF-THEN rules using pure structural analysis.

## Core Philosophy

**Tables are conditional logic structures.** Every data cell represents a logical conclusion derived from a specific set of row and column conditions. This system is built to parse that inherent logic and express it in a machine-readable format.

## Architecture: Adaptive Structural Analysis

Our final architecture was born from a rigorous development process. We discovered that simple content-based heuristics failed on complex tables, and a single tree-based approach wasn't universal enough. The breakthrough was Adaptive Structural Classification: the system first analyzes a table's structural patterns to classify its architecture, then applies the optimal processing path. This allows it to handle diverse layouts like business reports and conference schedules with production-ready accuracy.

## Key Features

* **Adaptive Processing**: Automatically detects table structure patterns and applies appropriate analysis method
* **True Universality**: Handles insurance tables, schedules, business reports, and any hierarchical table structure
* **Multi-Level Hierarchy Support**: Captures 3+ levels of nested headers (Region → Product → Quarter → Metric)
* **Structural Intelligence**: Distinguishes between content and structure without domain knowledge
* **Production Ready**: Successfully tested on complex real-world tables across different industries

## Usage

The script reads all HTML tables from `input.md` and writes the extracted logic rules to `output.md`.

```bash
python3 table2rules.py
```

## Example

This system can effortlessly handle complex hierarchical tables.

**Input Table:**

```html
<table>
  <tr>
    <th rowspan="2">Region</th>
    <th colspan="2">H1 Performance</th>
  </tr>
  <tr>
    <th>Sales</th>
    <th>Growth %</th>
  </tr>
  <tr>
    <td>Americas</td>
    <td>$5.2M</td>
    <td>+10%</td>
  </tr>
  <tr>
    <td>EMEA</td>
    <td>$3.8M</td>
    <td>+8%</td>
  </tr>
</table>
```

**Generated Rules:**

```
- IF "Americas" AND "H1 Performance" AND "Sales" THEN the value is '$5.2M'
- IF "Americas" AND "H1 Performance" AND "Growth %" THEN the value is '+10%'
- IF "EMEA" AND "H1 Performance" AND "Sales" THEN the value is '$3.8M'
- IF "EMEA" AND "H1 Performance" AND "Growth %" THEN the value is '+8%'
```

## RAG Integration

   The generated IF-THEN rules are optimized for Retrieval-Augmented Generation:

     - **Clean Semantic Content**: The rules contain only the logical conditions and outcomes, with no positional metadata noise.
     - **Natural Language Format**: The structure is easily embedded and understood by Large Language Models.
     - **Atomic Rules**: Each rule captures one precise logical relationship, reducing ambiguity and improving retrieval accuracy.
     - **Queryable Structure**: Allows for targeted information retrieval to answer highly specific questions.

## Use Cases
* **Knowledge Base Creation**: Transform archives of documents containing tables into a searchable, logical rule database.
* **Data Analysis**: Convert spreadsheets and reports into logical rules for automated reasoning and decision support.
* **Business Intelligence**: Extract and verify business logic from operational tables for process automation and compliance.