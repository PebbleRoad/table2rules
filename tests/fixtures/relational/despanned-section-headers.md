<!-- Two-column benefits schedule whose section headers were de-spanned by an
     OCR/HTML pipeline: the original full-width "1. ..." title cells lost their
     colspan and now appear as ordinary rows that carry no independent value.
     Col 0 carries no column header, so the descriptor-column rule promotes it
     to the row-label column (scope="row") — which means such a row would
     otherwise drop entirely. The de-spanned header rows must be PRESERVED
     (their text is real source content); dropping them silently loses the
     benefit names and leaves the repeated sub-item labels ("Each child insured
     person") context-less. We preserve the label verbatim rather than
     fabricate a section breadcrumb, because such a row is structurally
     indistinguishable from a leaf row with a genuinely missing value. This
     exercises the <td>+descriptor-promotion path, distinct from the explicit
     <th scope="row"> path in matrix/financial-nbsp-indented-rows.

     Two ways a de-spanned header arrives with "no independent value":
       - "1." / "2." rows: the value column is empty.
       - "3." row: the value column repeats the column header ("Sum Insured").
         clean_rules strips that self-echo, which would take the label with it
         unless the row is recognised as label-only first. -->
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
    <tr><td>3. COVID-19 coverage extension</td><td>Sum Insured</td></tr>
    <tr><td>Each adult insured person under 70</td><td>S$50,000</td></tr>
    <tr><td>Each child insured person</td><td>S$20,000</td></tr>
  </tbody>
</table>
