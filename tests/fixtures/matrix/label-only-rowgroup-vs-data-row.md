<!-- A label-only row is promoted to a row-group header only when it carries a
     SINGLE label cell. The first two columns here are row labels (no header
     text above them). "Region X" fills only the first label column with its
     value columns empty — a genuine group header, threaded as an ancestor of
     the rows beneath it. "Total | n=4" fills TWO label columns: it is a data
     row whose designated value columns merely happen to be empty, not a
     divider. Threading its cells as a group path would invent a breadcrumb and
     misattribute it onto rows below, so it stays on the is_label preservation
     path, emitted verbatim. -->
<table>
  <thead>
    <tr><th></th><th></th><th>A</th><th>B</th></tr>
  </thead>
  <tbody>
    <tr><td>Region X</td><td></td><td></td><td></td></tr>
    <tr><td>Asia</td><td>Japan</td><td>10</td><td>20</td></tr>
    <tr><td>Asia</td><td>Korea</td><td>30</td><td>40</td></tr>
    <tr><td>Total</td><td>n=4</td><td></td><td></td></tr>
  </tbody>
</table>
