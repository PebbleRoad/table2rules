<!-- Transposed roster form, headless and all <td>: row 0 has an empty corner
     beside per-entity column labels; every body row is label-only (one field
     name in col 0, all value cells blank). The empty-corner fallback must
     recognize row 0 as the column-header row and col 0 as the stub column —
     and the label-only body rows must stay row labels, NOT become rowgroup
     dividers (they group nothing). With zero data values the gate correctly
     reports no_candidate_data_cells and the table renders flat, preserving
     the full matrix. -->
<table><tbody><tr><td></td><td>Member 1</td><td>Member 2</td><td>Member 3</td></tr><tr><td>Family Name</td><td></td><td></td><td></td></tr><tr><td>Given Name</td><td></td><td></td><td></td></tr><tr><td>Citizenship</td><td></td><td></td><td></td></tr><tr><td>Organization</td><td></td><td></td><td></td></tr><tr><td>Signature</td><td></td><td></td><td></td></tr></tbody></table>
