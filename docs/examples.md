# Examples

A gallery of HTML inputs and their `rules`-format outputs. Each example
runs through the default entry point:

```python
from table2rules import process_tables_to_text
print(process_tables_to_text(html))
```

## Key-value table

```html
<table>
  <tr><th>Name</th><td>John Smith</td></tr>
  <tr><th>Department</th><td>Engineering</td></tr>
</table>
```

```
Name: John Smith
Department: Engineering
```

## Simple data table

```html
<table>
  <thead>
    <tr><th>Product</th><th>Price</th><th>Stock</th></tr>
  </thead>
  <tbody>
    <tr><td>Widget</td><td>$19.99</td><td>150</td></tr>
  </tbody>
</table>
```

```
Product: Widget
Price: $19.99
Stock: 150
```

## Multi-level column headers

```html
<table>
  <thead>
    <tr><th rowspan="2">Region</th><th colspan="2">Q1 Sales</th></tr>
    <tr><th>Revenue</th><th>Units</th></tr>
  </thead>
  <tbody>
    <tr><th>North</th><td>$50,000</td><td>500</td></tr>
  </tbody>
</table>
```

```
North | Q1 Sales > Revenue: $50,000
North | Q1 Sales > Units: 500
```

## Complex hierarchical table

Three-level column headers plus row-header rowspan.

```html
<table>
  <thead>
    <tr>
      <th rowspan="3">Region</th>
      <th rowspan="3">Unit</th>
      <th colspan="2">Q1</th>
    </tr>
    <tr><th colspan="2">Sales</th></tr>
    <tr><th>Rev</th><th>Cost</th></tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="2">NA</th>
      <th>East</th>
      <td>100</td><td>80</td>
    </tr>
    <tr><th>West</th><td>120</td><td>90</td></tr>
  </tbody>
</table>
```

```
NA > East | Q1 > Sales > Rev: 100
NA > East | Q1 > Sales > Cost: 80
NA > West | Q1 > Sales > Rev: 120
NA > West | Q1 > Sales > Cost: 90
```

## Clinical-trial output (sample)

A real-world clinical-trial table with four-level headers, three regions,
nine sites, and twelve outcome columns produces output like this (excerpt):

```
North America > Dr. Smith (Boston) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > Responders: 67%
Europe > Dr. Dubois (Paris) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > p-value: <0.001
Asia-Pacific > Dr. Tanaka (Tokyo) | Treatment Outcomes > Placebo (Control) > Secondary Endpoint > 95% CI: [-2.3, 4.7]
Pooled Analysis (All Sites) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > Responders: 68%
```

Every line is self-contained: the row-header path identifies the subject
(region > investigator) and the col-header path identifies the measurement
(arm > endpoint > metric). No line loses meaning when chunked out of
context.
