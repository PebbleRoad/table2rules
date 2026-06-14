<!-- Real docling schedule shape: a narrow label-only TITLE row immediately
     followed by a full-width <td colspan=N> DESCRIPTION band, then the value
     sub-rows. Both must thread, title as the outer ancestor:

       9. Trip Cancellation > If your trip is cancelled... > 1. Adult ... | value

     Two bugs combined here, both fixed:
     - The title's row-group extent must extend THROUGH the adjacent description
       band (which is itself a full-width band) to reach the value rows; before,
       the band terminated the extent and the title was dropped.
     - In a two-column Label|Value schedule the left column is the row-label/stub
       even though it carries a thead header ("Benefit"), which the multi-row /
       rowspan header signals miss (Signal D).

     The trailing "11. Trip Postponement" has no value rows under it, so it stays
     an is_label note rather than creating an empty group. -->
<table>
  <thead><tr><th>Benefit</th><th>Maximum limit (S$)</th></tr></thead>
  <tbody>
    <tr><td>9. Trip Cancellation</td><td></td></tr>
    <tr><td colspan="2">If your trip is cancelled due to specified events before departure.</td></tr>
    <tr><td>1. Adult insured person</td><td>5,000</td></tr>
    <tr><td>2. Child insured person</td><td>2,500</td></tr>
    <tr><td>10. Travel Delay</td><td></td></tr>
    <tr><td colspan="2">If the departure of your public transport is delayed by at least six hours.</td></tr>
    <tr><td>1. Adult insured person</td><td>100 per six hours up to 1,500</td></tr>
    <tr><td>2. Child insured person</td><td>50 per six hours up to 1,500</td></tr>
    <tr><td>11. Trip Postponement</td><td></td></tr>
  </tbody>
</table>
