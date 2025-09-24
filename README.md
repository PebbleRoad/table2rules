# table2rules

A universal system that transforms well-formed HTML tables into queryable IF-THEN rules using factory-based processor architecture and HTML semantic analysis.

## Core Philosophy

**Tables encode conditional logic through HTML structure.** Every data cell represents a logical conclusion derived from its row and column header context. This system extracts that inherent logic using HTML table semantics and expresses it in machine-readable formats optimized for RAG systems, knowledge bases, and automated reasoning.

## Architecture: Factory-Based Universal Processing

The system uses HTML table standards to achieve universal processing:

1. **HTML Semantic Parsing**: Converts tables to normalized grid format with proper span handling
2. **Factory-Based Routing**: Automatically selects optimal processor based on table structure
3. **HTML Standards Compliance**: Leverages `th`/`td` semantics for reliable structure vs content detection
4. **Multi-Format Output**: Generates RAG-optimized rules in multiple natural language formats

This enables reliable processing of any properly structured HTML table without content-specific configuration.

## Key Features

### Universal HTML Table Support
* **Hierarchical Tables**: Complex business data with spanning row/column headers
* **Conference Schedules**: Multi-day, multi-track event programming
* **Financial Reports**: Sales performance, budgets, enterprise program tracking
* **Form Tables**: Input forms with label-value pair extraction
* **Layout Tables**: Spatial content arrangements with linearization

### Advanced Hierarchical Processing
* **Multi-Level Headers**: Handles 3+ level hierarchies (Program → Project → Phase → Metric)
* **Complex Spanning**: Processes any rowspan/colspan combination correctly
* **Shared Resources**: Handles cells spanning multiple logical entities
* **HTML Semantic Compliance**: Requires proper `th` for headers, `td` for data

### RAG System Integration
* **Complete Context Preservation**: "Americas Alpha Quarter Q1 Actual, the content is 3.2"
* **Multiple Output Formats**: Descriptive, conversational, searchable, structured formats
* **Vector Database Ready**: Embedding-optimized natural language generation
* **Full Semantic Context**: Every rule contains complete hierarchical context

## Usage

### Basic Usage
```bash
python3 table2rules.py --format descriptive
```

### Advanced Options
```bash
# Different output formats
python3 table2rules.py --format conversational
python3 table2rules.py --format structured  
python3 table2rules.py --format searchable

# Verbose processor selection debugging
python3 table2rules.py --format descriptive --verbose
```

## Example Transformations

### Conference Schedule
**Input:**
```html
<table>
  <thead>
    <tr><th></th><th colspan="2">Day 1</th></tr>
    <tr><th>Track</th><th>09:00</th><th>14:00</th></tr>
  </thead>
  <tbody>
    <tr><td rowspan="2">AI</td><td>Opening Keynote</td><td>Deploying at Scale</td></tr>
    <tr><td>Vision 101</td><td>Monitoring</td></tr>
  </tbody>
</table>
```

**Output:**
```
AI Day 1 09:00, the content is Opening Keynote
AI Day 1 14:00, the content is Deploying at Scale
AI Day 1 09:00, the content is Vision 101
AI Day 1 14:00, the content is Monitoring
```

### Financial Performance Report
**Input:**
```html
<table>
  <thead>
    <tr>
      <th rowspan="3">Region</th>
      <th rowspan="3">Product</th>
      <th colspan="4">Quarter</th>
    </tr>
    <tr>
      <th colspan="2">Q1</th>
      <th colspan="2">Q2</th>
    </tr>
    <tr>
      <th>Actual</th><th>Target</th>
      <th>Actual</th><th>Target</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="2">Americas</th>
      <th>Alpha</th>
      <td>3.2</td><td>3.0</td><td>3.8</td><td>3.5</td>
    </tr>
  </tbody>
</table>
```

**Output:**
```
Americas Alpha Quarter Q1 Actual, the content is 3.2
Americas Alpha Quarter Q1 Target, the content is 3.0  
Americas Alpha Quarter Q2 Actual, the content is 3.8
Americas Alpha Quarter Q2 Target, the content is 3.5
```

### Enterprise Program Tracking
**Input:**
```html
<table>
  <thead>
    <tr>
      <th rowspan="3">Program</th>
      <th rowspan="3">Project</th>
      <th colspan="6">Phase Gates</th>
    </tr>
    <tr>
      <th colspan="2">Discovery</th>
      <th colspan="2">Build</th>
      <th colspan="2">Launch</th>
    </tr>
    <tr>
      <th>Plan</th><th>Actual</th>
      <th>Plan</th><th>Actual</th>
      <th>Plan</th><th>Actual</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="2">Program Atlas</th>
      <th>Aquila</th>
      <td>Jan</td><td>Jan</td><td>Mar</td><td>Apr</td><td>Jun</td><td>Jun</td>
    </tr>
  </tbody>
</table>
```

**Output:**
```
Program Atlas Aquila Phase Gates Discovery Plan, the content is Jan
Program Atlas Aquila Phase Gates Discovery Actual, the content is Jan
Program Atlas Aquila Phase Gates Build Plan, the content is Mar
Program Atlas Aquila Phase Gates Build Actual, the content is Apr
Program Atlas Aquila Phase Gates Launch Plan, the content is Jun
Program Atlas Aquila Phase Gates Launch Actual, the content is Jun
```

## Supported Table Patterns

### Successfully Processed
- **Multi-level hierarchies** with complex spanning patterns
- **Conference schedules** with day/time/track matrices
- **Financial reports** with region/product/metric breakdowns
- **Enterprise tracking** with program/project/phase structures
- **Any properly structured business table** using HTML semantics

### HTML Compliance Requirements
- **Headers must use `<th>` elements** (not `<td>`)
- **Data content must use `<td>` elements** 
- **Proper spanning via `rowspan`/`colspan` attributes**
- **Semantic structure** with `<thead>`, `<tbody>`, optional `<tfoot>`

### Known Limitations
- **Malformed HTML tables** using `<td>` for structural headers will fail gracefully
- **Tables without proper semantic structure** cannot be reliably processed
- **Layout abuse** (tables used purely for visual positioning) not supported

## Output Formats

### Descriptive (RAG Optimized)
Complete semantic context for vector similarity search:
```
Americas Alpha Quarter Q1 Actual, the content is 3.2
```

### Conversational  
Natural language for chat interfaces:
```
For Americas Alpha Quarter Q1 Actual, the value is 3.2
```

### Structured
Formal IF-THEN logic rules:
```
IF "Americas" AND "Alpha" AND "Quarter Q1 Actual" THEN the value is '3.2'
```

### Searchable
Keyword-optimized for search systems:
```
Americas Alpha Quarter Q1 Actual value amount 3.2
```

## Technical Architecture

```
HTML Input → Parse & Normalize → Factory Router → Specialized Processor → Multi-Format Output
     ↓              ↓                ↓                    ↓                     ↓
HTML Validation  Grid Creation   Confidence Scoring   Context Assembly   Natural Language
                                                                         Generation
```

### Processor Types
- **HierarchicalRowTableProcessor**: Complex spanning row structures (primary)
- **DataTableProcessor**: Standard business data tables (fallback)
- **FormTableProcessor**: Label-value pair extraction
- **LayoutTableProcessor**: Content linearization

### Core Components
- **Factory-based routing** with confidence scoring
- **HTML semantic analysis** using `th`/`td` distinction
- **Multi-level context assembly** from spanning headers
- **RAG-optimized natural language generation**

## Production Characteristics

### Performance
- **Processing Speed**: Complex tables processed in <1 second
- **Memory Usage**: Single-pass processing with minimal state
- **Scalability**: Handles 100+ row tables with deep hierarchies

### Reliability
- **HTML Standards Compliance**: Predictable behavior for well-formed tables
- **Graceful Failure**: Clear error messages for malformed input
- **Test Coverage**: Validated on conference, financial, and enterprise table patterns

### Integration
- **Simple CLI**: Single command processing with format selection
- **API Ready**: Clean processor interfaces for embedding in larger systems
- **Batch Processing**: Factory architecture enables parallel processing

## Use Cases

### RAG Systems
Transform structured business data into embedding-friendly rules for semantic search, question-answering, and knowledge retrieval systems.

### Knowledge Extraction
Convert document archives containing tables into queryable knowledge bases for compliance, customer support, and decision support systems.

### Business Intelligence
Extract conditional logic from spreadsheets and reports for automated reasoning, process automation, and business rule engines.

### Document Processing
Integrate into larger document analysis pipelines for comprehensive structured data extraction from mixed content types.

## Architecture Benefits

The factory-based approach with HTML semantic processing provides:

- **Universal Coverage**: Handles any well-formed HTML table structure
- **No Configuration Required**: Automatic table type detection and processing
- **Reliable Extraction**: HTML standards provide predictable semantic patterns
- **RAG Optimization**: Output formats designed for modern retrieval systems
- **Production Ready**: Clean error handling and diagnostic feedback

This architecture demonstrates that HTML table standards provide sufficient structure for universal table processing without requiring content-specific pattern matching or domain-specific rules.