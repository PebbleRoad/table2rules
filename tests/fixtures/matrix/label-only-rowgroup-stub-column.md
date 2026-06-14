<!-- Multi-column matrix variant: a label-only group header sits in the leading
     stub/line-number column while the sub-rows leave that column empty and carry
     their identity in a different column ("10. Travel Delay" in col 0; the rows
     beneath it are "Adult under 70" / "Child" in col 1, col 0 empty).

     A label-only band groups a ROW RANGE, so it must reach every value row in
     its extent regardless of which column its single label cell occupies — the
     maze scans all columns for these bands. Without that reach the band is
     unreachable from the value rows (their own column and row-label column never
     touch col 0) and the group header is dropped entirely. Each group's extent
     still closes at the next group, so "9." does not leak onto "10."'s rows. -->
<table>
  <tbody>
    <tr><th rowspan="2" colspan="2">SECTION</th><th colspan="2">PLANS</th></tr>
    <tr><th>BASIC</th><th>ELITE</th></tr>
    <tr><td>9. Trip Cancellation</td><td></td><td></td><td></td></tr>
    <tr><td></td><td>If the trip is cancelled</td><td>5,000</td><td>10,000</td></tr>
    <tr><td>10. Travel Delay</td><td></td><td></td><td></td></tr>
    <tr><td></td><td>Adult under 70</td><td>100</td><td>200</td></tr>
    <tr><td></td><td>Child</td><td>50</td><td>100</td></tr>
  </tbody>
</table>
