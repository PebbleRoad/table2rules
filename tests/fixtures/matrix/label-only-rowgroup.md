<!-- Label-only rows as row-group headers. A body row whose value columns are
     empty and whose single leading label cell carries text ("9. Trip
     Cancellation") is a group header, not an orphan — the Label|Value form
     pervasive in financial/insurance schedules. Unlike a full-width band the
     label cell does NOT span the value region; the other columns are simply
     empty, so is_full_width_note geometry never sees it.

     Each such header is threaded as a row-group ancestor of every value row
     beneath it, until the next label-only row at the same level — so a value
     never loses its line-item identity. A stack of consecutive label-only rows
     (a title followed by a description, "10. Travel Delay" then "If the
     departure…") nests in order, title first. -->
<table>
  <thead>
    <tr><th rowspan="2">Benefit</th><th colspan="2">Maximum limit (S$)</th></tr>
    <tr><th>Value Plan</th><th>Economy Plan</th></tr>
  </thead>
  <tbody>
    <tr><td>9. Trip Cancellation</td><td></td><td></td></tr>
    <tr><td>If the trip is cancelled</td><td>5,000</td><td>10,000</td></tr>
    <tr><td>10. Travel Delay</td><td></td><td></td></tr>
    <tr><td>If the departure is delayed</td><td></td><td></td></tr>
    <tr><td>1. Adult insured person</td><td>100</td><td>150</td></tr>
    <tr><td>2. Child insured person</td><td>50</td><td>75</td></tr>
    <tr><td>11. Trip Postponement</td><td></td><td></td></tr>
  </tbody>
</table>
