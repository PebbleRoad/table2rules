# table2rules: Technical Implementation Guide

## Project Overview

table2rules implements a universal system that transforms HTML tables into queryable IF-THEN rules using a factory-based processor architecture. The system automatically identifies table types and routes them to specialized processors, achieving true separation of concerns while maintaining universal coverage for well-formed HTML tables.

## Validated Universal Architecture (2025)

### Factory-Based Processing Pipeline
1. **HTML Table Parsing**: Robust parsing with rowspan/colspan unmerging into normalized grid
2. **Confidence-Based Routing**: Factory pattern automatically selects optimal processor
3. **HTML-Semantic Processing**: Each processor leverages HTML table semantics for reliable extraction
4. **RAG-Optimized Output**: Multi-format rule generation optimized for retrieval systems

### Proven Table Type Coverage
- **Hierarchical Tables**: Complex business data with spanning row/column headers
- **Conference Schedules**: Multi-day, multi-track event programming
- **Financial Reports**: Sales performance, budgets, enterprise program tracking
- **Form Tables**: Input forms with label-value pair extraction
- **Layout Tables**: Spatial content arrangements

## Core Technical Innovations

### 1. HTML Standards-Based Universal Processing

**Key Insight**: HTML table standards provide finite, predictable semantic patterns that enable truly universal processing without content-specific rules.

**HTML Semantic Awareness**:
```python
# Structural detection using HTML semantics, not content patterns
def _build_row_context_map(self, grid):
    for cell in original_cells:
        cell_type = cell.get('type')
        # ONLY header cells (th) can be hierarchical identifiers
        if cell_type != 'th':
            continue
        # Process spanning and single-row headers...
```

### 2. Factory-Based Processor Architecture

**Clean Routing Logic**:
```python
class TableProcessorFactory:
    def process_table(self, grid, table_element):
        # Confidence-based processor selection
        scores = [(p, p.can_process(grid, table_element)) for p in self.processors]
        best_processor = max(scores, key=lambda x: x[1])[0]
        return best_processor.process(grid, table_element)
```

**Processor Hierarchy**:
- **HierarchicalRowTableProcessor**: Handles spanning row headers (conferences, financial reports)
- **DataTableProcessor**: Standard business data tables  
- **FormTableProcessor**: Label-value pair extraction
- **LayoutTableProcessor**: Content linearization

### 3. Hierarchical Row Table Processing (Primary Innovation)

**Universal Spanning Detection**:
```python
def can_process(self, grid, table_element):
    # Detects hierarchical structure via HTML semantics
    spanning_headers = sum(1 for cell in grid 
                          if cell.get('original_rowspan', 1) > 1 
                          and self._is_structural_header(cell))
    return confidence_score_based_on_structure
```

**Multi-Level Context Assembly**:
- Row context from spanning headers ("Americas", "Program Atlas")
- Column context from hierarchical headers ("Quarter Q1 Actual", "Phase Gates Discovery Plan")  
- Clean separation of structure vs content using `th`/`td` semantics

### 4. RAG-Optimized Output Generation

**Complete Semantic Context**:
```python
# Example outputs demonstrate full context preservation
"Americas Alpha Quarter Q1 Actual, the content is 3.2"
"Program Atlas Aquila Phase Gates Discovery Plan, the content is Jan" 
"Day 1 Mon, 12 May 09:00 Tracks A — Main Hall, the content is Opening Keynote"
```

**Multi-Format Support**:
- **Descriptive**: Full semantic context for RAG systems
- **Conversational**: Natural language for chat interfaces
- **Searchable**: Keyword-optimized for search systems
- **Structured**: Formal IF-THEN logic rules

## Implementation Architecture

### Core File Structure
```
table2rules.py              # Core parsing, LogicRule class, CLI
table_processors.py         # All processor implementations
table_processor_factory.py  # Factory routing and orchestration
```

### Processor Class Hierarchy
```python
class TableProcessor(ABC):
    def can_process(grid, table_element) -> float    # Confidence scoring
    def process(grid, table_element) -> ProcessingResult  # Processing logic

class HierarchicalRowTableProcessor(TableProcessor):
    # Handles complex spanning row structures
    # Validated on: conferences, sales reports, enterprise programs
    
class DataTableProcessor(TableProcessor):  
    # Standard business data tables
    # Fallback for simple hierarchical structures
    
class FormTableProcessor(TableProcessor):
    # Label-value pair extraction
    
class LayoutTableProcessor(TableProcessor):
    # Spatial content linearization
```

### Processing Pipeline
```
HTML Input → Parse & Normalize → Factory Confidence Scoring → 
Specialized Processing → Context Assembly → Multi-Format Output
```

## Validated Capabilities

### ✅ Complex Hierarchical Processing
**Real-World Examples Successfully Processed**:

**Conference Schedule**:
```
AI Day 1 09:00, the content is Opening Keynote
Data Day 1 14:00, the content is dbt Patterns  
Day 1 Mon, 12 May 09:00 Tracks A — Main Hall, the content is Opening Keynote
```

**Financial Performance**:
```
Americas Alpha Quarter Q1 Actual, the content is 3.2
EMEA Beta H1 (Q1 + Q2) Target, the content is 3.7
APAC APAC Subtotal (Alpha + Beta) Variance, the content is +0.2
```

**Enterprise Programs**:
```
Program Atlas Aquila Phase Gates Discovery Plan, the content is Jan
Program Nimbus Daedalus Budget (USD M) CapEx, the content is 4.5
Program Nimbus Icarus Status, the content is Risk Watch
```

### ✅ Advanced Spanning Scenarios
- **Multi-level column hierarchies**: "Phase Gates" → "Discovery" → "Plan"
- **Complex row spanning**: Program headers spanning multiple projects
- **Mixed spanning patterns**: Both rowspan and colspan in same table
- **Shared resources**: CapEx cells spanning multiple projects
- **Consolidated phases**: Merged timeline cells with descriptive content

### ✅ HTML Semantic Compliance
- Proper `th` vs `td` distinction for structure vs content
- `scope` attribute recognition (row, col, rowgroup, colgroup)
- `rowspan`/`colspan` handling with proper context propagation
- `thead`, `tbody`, `tfoot` section awareness
- Graceful handling of malformed tables (fails appropriately)

## Technical Architecture Benefits

### Universal Coverage Through HTML Standards
**Key Principle**: Well-formed HTML tables have finite, predictable patterns defined by W3C standards.

**Eliminated Complexity**:
- No content-pattern matching required
- No domain-specific rules needed
- No manual table type classification
- No custom configuration per table format

**Architectural Strengths**:
- **Maintainability**: HTML semantics provide stable foundation
- **Debuggability**: Clear processor selection and context building
- **Extensibility**: New processors follow established HTML-semantic patterns  
- **Testability**: Each processor handles distinct HTML patterns
- **Universality**: Covers any properly structured hierarchical table

### Performance Characteristics
- **Routing Efficiency**: O(1) confidence scoring per processor
- **Context Building**: O(n²) where n = table dimensions (optimal for grid processing)
- **Memory Usage**: Single-pass processing with minimal state retention
- **Scalability**: Processors operate independently, enabling parallel processing

## Production Deployment

### CLI Usage
```bash
# Process with automatic processor selection
python3 table2rules.py --format descriptive input.md

# Debug processor selection
python3 table2rules.py --format descriptive --verbose input.md
```

### Integration API
```python
from table2rules import process_table
rules = process_table(html_table_string)
# Returns ProcessingResult with rules, metadata, confidence scores
```

### Supported Input Formats
- Raw HTML table strings
- Markdown files containing HTML tables
- Well-formed tables from any HTML source

### Output Formats
- **descriptive**: Full context for RAG systems
- **conversational**: Natural language for interfaces
- **structured**: Formal IF-THEN logic rules
- **searchable**: Keyword-optimized content

## Validation Results

### Test Coverage
**Successfully Processed Table Types**:
- Conference schedules (2-3 day, multi-track)
- Financial performance reports (regional, product, temporal hierarchies)
- Enterprise program tracking (phase gates, budgets, status)
- Sales data (multi-dimensional breakdowns)
- Any properly structured hierarchical business table

**HTML Compliance Requirements**:
- Headers must use `th` elements (not `td`)
- Data content must use `td` elements
- Spanning relationships via `rowspan`/`colspan` attributes
- Proper semantic structure (`thead`, `tbody`, optional `tfoot`)

### Failure Cases (By Design)
**Malformed HTML Tables**:
- Tables using `td` for structural headers (insurance table example)
- Missing semantic structure (all content in `td` without proper headers)
- Extreme layout abuse (tables used purely for visual positioning)

**Resolution**: These failures are correct behavior - the system properly identifies and rejects semantically invalid table markup.

## Future Extensions

### Planned Enhancements
1. **Custom Processors**: Domain-specific processors following HTML-semantic patterns
2. **Batch Processing**: Factory-coordinated processing of table collections
3. **Validation Tools**: HTML table semantic validation and repair suggestions
4. **Performance Monitoring**: Detailed processor selection and timing metrics

### Integration Opportunities
1. **Document Processing Pipelines**: Integration with larger document analysis systems
2. **RAG System Integration**: Direct pipeline to vector databases and search systems
3. **Data Extraction Services**: Microservice architecture for table processing at scale
4. **Content Management**: Automated rule generation for content repositories

## Research Impact

This implementation validates a fundamental hypothesis: **HTML table standards provide sufficient semantic structure for universal table processing**. 

The finite permutations of well-formed HTML table markup can be reliably processed using:
1. **Structural detection** via HTML element semantics
2. **Factory-based routing** for processor specialization  
3. **Context-aware rule generation** for downstream systems
4. **Multi-format output** for diverse integration needs

This approach eliminates the need for content-specific pattern matching or domain-specific table processing rules, achieving true universality through adherence to existing web standards.

The factory-based architecture demonstrates how clean separation of concerns enables both reliability and extensibility in complex data processing systems, providing a template for other universal content processing challenges.