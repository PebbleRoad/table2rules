<!-- A benefit matrix with a multi-level plan×cover header (8 logical columns).
     Some body rows are full-width descriptions, encoded as a marker cell plus a
     <td colspan="7"> that spans the entire value region:

         <td>1</td><td colspan="7">Accidental death and permanent disability</td>

     Such a cell is a group header / description (NOT a per-column value), so it
     must not be fanned out across every spanned value column. Detected purely
     geometrically — it reaches the last column AND spans a majority of the
     grid's columns — it becomes a row-group band: its label threads into the
     row path of the rows it groups ("Accidental death … > 1 > Each adult
     insured person under 70 | … VALUE PLAN > INDIVIDUAL COVER: 150,000"), with
     the person-class column threaded too (the "SECTION" stub dimension, Signal
     C). Legitimate narrow spans — the colspan="2" amount covering
     INDIVIDUAL+FAMILY of one plan, e.g. "Up to 30 days" — fail the majority
     test and keep their per-column fan-out. -->
<table>
  <thead>
    <tr><th rowspan="3" colspan="2">SECTION</th><th colspan="6">MAXIMUM LIMIT OF BENEFIT (S$)</th></tr>
    <tr><th colspan="2">VALUE PLAN</th><th colspan="2">ECONOMY PLAN</th><th colspan="2">PREMIUM PLAN</th></tr>
    <tr><th>INDIVIDUAL COVER</th><th>FAMILY COVER</th><th>INDIVIDUAL COVER</th><th>FAMILY COVER</th><th>INDIVIDUAL COVER</th><th>FAMILY COVER</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td colspan="7">Accidental death and permanent disability</td></tr>
    <tr><td>1</td><td>Each adult insured person under 70</td><td>150,000</td><td>300,000 in total</td><td>250,000</td><td>650,000 in total</td><td>500,000</td><td>1,250,000 in total</td></tr>
    <tr><td>17</td><td colspan="7">Automatic extension of cover</td></tr>
    <tr><td>17</td><td>Extended period of cover</td><td colspan="2">Up to 30 days</td><td colspan="2">Up to 30 days</td><td colspan="2">Up to 30 days</td></tr>
  </tbody>
</table>
