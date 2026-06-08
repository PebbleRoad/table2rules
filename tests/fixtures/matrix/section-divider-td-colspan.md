<!-- A multi-row-header matrix with body section dividers encoded as single
     full-width <td colspan="4"> rows ("Section One", "Section Two"). There is
     no explicit <thead>, so the header boundary is detected structurally.

     The trap: a single <td colspan="4"> cell expands to 4 non-empty logical
     positions, so the colspan-expanded cell count reads it as a full header
     row. Without the divider-series cap, the header sweep swallows the FIRST
     divider and the data row beneath it into the <thead>, and they then bleed
     onto every body line as fabricated column headers. With the cap, a series
     of >= 2 full-width single-cell rows is recognised as body section dividers:
     the header ends at the first one, and the dividers stay in the body as
     full-width notes (emitted once each), never promoted to <th scope="row">
     (which would strand them, as they have no value column to anchor a rule). -->
<table>
  <tbody>
    <tr><th rowspan="2">No.</th><th rowspan="2">Item</th><th colspan="2">Values</th></tr>
    <tr><th>X</th><th>Y</th></tr>
    <tr><td colspan="4">Section One</td></tr>
    <tr><td>1</td><td>alpha</td><td>10</td><td>20</td></tr>
    <tr><td>2</td><td>beta</td><td>11</td><td>21</td></tr>
    <tr><td colspan="4">Section Two</td></tr>
    <tr><td>3</td><td>gamma</td><td>30</td><td>40</td></tr>
    <tr><td>4</td><td>delta</td><td>31</td><td>41</td></tr>
  </tbody>
</table>
