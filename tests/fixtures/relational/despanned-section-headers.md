<!-- Two-column benefits schedule whose section headers were de-spanned by an
     OCR/HTML pipeline: the original full-width "1. ..." / "2. ..." title cells
     lost their colspan and now appear as ordinary rows with an empty value
     column. Col 0 carries no column header, so the descriptor-column rule
     promotes it to the row-label column (scope="row") — which means an empty
     value column would otherwise drop the whole row. The de-spanned header
     rows must be PRESERVED (their text is real source content); dropping them
     silently loses the benefit names and leaves the repeated sub-item labels
     ("Each child insured person") context-less. We preserve the label verbatim
     rather than fabricate a section breadcrumb, because an empty-value row is
     structurally indistinguishable from a leaf row with a genuinely missing
     value. This exercises the <td>+descriptor-promotion path, distinct from
     the explicit <th scope="row"> path in matrix/financial-nbsp-indented-rows. -->
<table>
  <thead>
    <tr><th></th><th>Sum Insured</th></tr>
  </thead>
  <tbody>
    <tr><td>1. Accidental death and permanent disability</td><td></td></tr>
    <tr><td>Each adult insured person under 70</td><td>S$250,000</td></tr>
    <tr><td>Each child insured person</td><td>S$100,000</td></tr>
    <tr><td>2. Public transport double indemnity</td><td></td></tr>
    <tr><td>Each adult insured person under 70</td><td>S$500,000</td></tr>
    <tr><td>Each child insured person</td><td>S$200,000</td></tr>
  </tbody>
</table>
