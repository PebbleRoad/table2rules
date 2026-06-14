<!-- Real docling matrix shape: a repeating number-KEY column (col 0, "10"
     repeated on every row of the group, from an expanded rowspan), a benefit
     descriptor column (col 1), then plan x cover value columns. Each group is a
     label-only TITLE row ("10 | Travel delay | <empty values>") followed by a
     full-width DESCRIPTION band, then the value sub-rows.

     The title "Travel delay" is a multi-cell label-only row (number key + title)
     — at most one numeric label cell, so it is a group header, not a data row.
     The repeating key "10" is excluded from the promoted title (it already
     threads via the value rows' own key cell); only "Travel delay" is threaded,
     so the path carries the line-item identity without duplicating the number. -->
<table>
  <thead>
    <tr><th rowspan="2"></th><th rowspan="2"></th><th colspan="2">Value Plan</th><th colspan="2">Economy Plan</th></tr>
    <tr><th>Individual</th><th>Family</th><th>Individual</th><th>Family</th></tr>
  </thead>
  <tbody>
    <tr><td>9</td><td>Trip Cancellation</td><td colspan="4"></td></tr>
    <tr><td>9</td><td colspan="5">If your trip is cancelled due to specified events.</td></tr>
    <tr><td>9</td><td>1. Adult insured person</td><td>5,000</td><td>10,000</td><td>3,000</td><td>6,000</td></tr>
    <tr><td>9</td><td>2. Child insured person</td><td>2,500</td><td>5,000</td><td>1,500</td><td>3,000</td></tr>
    <tr><td>10</td><td>Travel delay</td><td colspan="4"></td></tr>
    <tr><td>10</td><td colspan="5">If the departure of your public transport is delayed by six hours.</td></tr>
    <tr><td>10</td><td>1. Adult insured person</td><td>100</td><td>200</td><td>150</td><td>300</td></tr>
    <tr><td>10</td><td>2. Child insured person</td><td>50</td><td>100</td><td>75</td><td>150</td></tr>
  </tbody>
</table>
