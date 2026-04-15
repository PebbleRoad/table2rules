<table>
  <tr><th colspan="3">Operations Ledger 2026</th></tr>
  <tr><th>Section</th><th>Metric</th><th>Value</th></tr>

  <tr>
    <td rowspan="foo">North</td>
    <td>Revenue</td>
    <td>$120</td>
  </tr>
  <tr>
    <td>Cost</td>
    <td>
      <table>
        <tr><td>USD</td><td>80</td></tr>
      </table>
    </td>
  </tr>
  <tr><td>North</td><td>Notes</td><td>line 1<br>line 2<sup>*</sup></td></tr>

  <!-- mid-body reset, multi-row style -->
  <tr><th>Section</th><th>Metric</th><th>Value</th></tr>
  <tr><th>South</th><th>Revenue</th><th>130</th></tr>
  <tr><td>South</td><td>Cost</td><td colspan="0">90</td></tr>
  <tr><td>South</td><td>Cost</td><td colspan="-1">91</td></tr>

  <!-- sparse row that should not be blindly merged away -->
  <tr><td>South</td><td></td><td></td></tr>

  <tr><th>Total</th><th></th><th>220</th></tr>
  <tr><td colspan="3">Legend: * includes one-off adjustment</td></tr>
</table>
