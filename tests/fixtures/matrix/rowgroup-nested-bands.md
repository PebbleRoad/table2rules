<!-- Hierarchical row-groups threaded into each value line, symmetric with the
     multi-level column header path. The row hierarchy is distinguished by
     colspan: a full-width <td colspan="4"> is a section band; a value-region-
     wide <td colspan="3"> (after the rownum) is a benefit group header; the
     narrow first columns are the row label (rownum + person-class). The
     leftmost top-level header "SECTION" (colspan 2) marks the row-label
     dimension, so the person-class column threads too (Signal C).

     Each value line carries its full row path — band > benefit > rownum >
     person-class — so one line maps to exactly one record with no stateful
     reconstruction. The last row has an EMPTY rownum cell: its band ("2.
     MEDICAL") is still found by walking the value cell's own column (the band
     spans it), which a row-label-only walk would miss. -->
<table>
  <tbody>
    <tr><th rowspan="2" colspan="2">SECTION</th><th colspan="2">PLANS</th></tr>
    <tr><th>BASIC</th><th>ELITE</th></tr>
    <tr><td colspan="4">1. ACCIDENT</td></tr>
    <tr><td>1</td><td colspan="3">Accidental death and disability</td></tr>
    <tr><td>1</td><td>Adult under 70</td><td>100</td><td>200</td></tr>
    <tr><td>1</td><td>Child</td><td>50</td><td>100</td></tr>
    <tr><td colspan="4">2. MEDICAL</td></tr>
    <tr><td>2</td><td colspan="3">Overseas expenses</td></tr>
    <tr><td>2</td><td>Adult under 70</td><td>300</td><td>400</td></tr>
    <tr><td></td><td>Child</td><td>150</td><td>250</td></tr>
  </tbody>
</table>
