<table>
  <caption>FY2025 Sales Performance — Regional & Product Breakdown (H1)</caption>

  <!-- Column sizing is optional but helpful when testing layout -->
  <colgroup>
    <col span="1" style="width: 12rem;">   <!-- Region -->
    <col span="1" style="width: 12rem;">   <!-- Product -->
    <col span="4" style="width: 7rem;">    <!-- Q1/Q2 Actual/Target -->
    <col span="2" style="width: 7rem;">    <!-- H1 Actual/Target -->
    <col span="1" style="width: 8rem;">    <!-- Variance -->
    <col span="1" style="width: 18rem;">   <!-- Notes -->
  </colgroup>

  <thead>
    <tr>
      <th id="h-region" scope="col" rowspan="3">Region</th>
      <th id="h-product" scope="col" rowspan="3">Product</th>

      <!-- Top-level grouped headers -->
      <th id="h-quarter" scope="colgroup" colspan="4">Quarter</th>
      <th id="h-h1" scope="colgroup" colspan="2">H1 (Q1 + Q2)</th>
      <th id="h-var" scope="col" rowspan="3">Variance</th>
      <th id="h-notes" scope="col" rowspan="3">Notes</th>
    </tr>
    <tr>
      <!-- Second header row: split Quarter into Q1 and Q2 -->
      <th id="h-q1" scope="colgroup" colspan="2">Q1</th>
      <th id="h-q2" scope="colgroup" colspan="2">Q2</th>
      <th id="h-h1a" scope="col">Actual</th>
      <th id="h-h1t" scope="col">Target</th>
    </tr>
    <tr>
      <!-- Third header row: atomic columns -->
      <th id="h-q1a" scope="col">Actual</th>
      <th id="h-q1t" scope="col">Target</th>
      <th id="h-q2a" scope="col">Actual</th>
      <th id="h-q2t" scope="col">Target</th>
      <!-- H1 Actual/Target already defined above -->
    </tr>
  </thead>

  <tbody>
    <!-- AMERICAS group (rowgroup header spans 3 product rows) -->
    <tr>
      <th scope="rowgroup" rowspan="3" headers="h-region">Americas</th>
      <th scope="row" headers="h-product">Alpha</th>
      <td headers="h-quarter h-q1 h-q1a">3.2</td>
      <td headers="h-quarter h-q1 h-q1t">3.0</td>
      <td headers="h-quarter h-q2 h-q2a">3.8</td>
      <td headers="h-quarter h-q2 h-q2t">3.5</td>
      <td headers="h-h1 h-h1a">7.0</td>
      <td headers="h-h1 h-h1t">6.5</td>
      <td headers="h-var">+0.5</td>
      <td headers="h-notes">Beat targets due to Q2 promo.</td>
    </tr>
    <tr>
      <th scope="row" headers="h-product">Beta</th>
      <td headers="h-quarter h-q1 h-q1a">2.1</td>
      <td headers="h-quarter h-q1 h-q1t">2.4</td>
      <td headers="h-quarter h-q2 h-q2a">2.6</td>
      <td headers="h-quarter h-q2 h-q2t">2.8</td>
      <td headers="h-h1 h-h1a">4.7</td>
      <td headers="h-h1 h-h1t">5.2</td>
      <td headers="h-var">−0.5</td>
      <td headers="h-notes">Supply constraint in Q1.</td>
    </tr>
    <tr>
      <th scope="row" headers="h-product">Gamma</th>
      <td headers="h-quarter h-q1 h-q1a">1.4</td>
      <td headers="h-quarter h-q1 h-q1t">1.2</td>
      <td headers="h-quarter h-q2 h-q2a">1.9</td>
      <td headers="h-quarter h-q2 h-q2t">1.6</td>
      <td headers="h-h1 h-h1a">3.3</td>
      <td headers="h-h1 h-h1t">2.8</td>
      <td headers="h-var">+0.5</td>
      <td headers="h-notes">New channel launched mid-Q2.</td>
    </tr>

    <!-- EMEA group (rowgroup header spans 2 product rows; includes a cell with colspan to test mixed merging) -->
    <tr>
      <th scope="rowgroup" rowspan="2" headers="h-region">EMEA</th>
      <th scope="row" headers="h-product">Alpha</th>
      <td headers="h-quarter h-q1 h-q1a">2.8</td>
      <td headers="h-quarter h-q1 h-q1t">2.9</td>
      <td headers="h-quarter h-q2 h-q2a">3.0</td>
      <td headers="h-quarter h-q2 h-q2t">3.1</td>
      <td headers="h-h1 h-h1a">5.8</td>
      <td headers="h-h1 h-h1t">6.0</td>
      <td headers="h-var">−0.2</td>
      <td headers="h-notes">Currency headwinds.</td>
    </tr>
    <tr>
      <th scope="row" headers="h-product">Beta</th>
      <td headers="h-quarter h-q1 h-q1a">1.9</td>
      <td headers="h-quarter h-q1 h-q1t">1.7</td>
      <td headers="h-quarter h-q2 h-q2a">2.2</td>
      <td headers="h-quarter h-q2 h-q2t">2.0</td>
      <td headers="h-h1 h-h1a">4.1</td>
      <td headers="h-h1 h-h1t">3.7</td>
      <td headers="h-var">+0.4</td>
      <td headers="h-notes">Enterprise deal closed in Q2.</td>
    </tr>

    <!-- APAC group (rowgroup with a sub-total row that uses colspan) -->
    <tr>
      <th scope="rowgroup" rowspan="3" headers="h-region">APAC</th>
      <th scope="row" headers="h-product">Alpha</th>
      <td headers="h-quarter h-q1 h-q1a">3.5</td>
      <td headers="h-quarter h-q1 h-q1t">3.2</td>
      <td headers="h-quarter h-q2 h-q2a">3.9</td>
      <td headers="h-quarter h-q2 h-q2t">3.6</td>
      <td headers="h-h1 h-h1a">7.4</td>
      <td headers="h-h1 h-h1t">6.8</td>
      <td headers="h-var">+0.6</td>
      <td headers="h-notes">Seasonal lift.</td>
    </tr>
    <tr>
      <th scope="row" headers="h-product">Beta</th>
      <td headers="h-quarter h-q1 h-q1a">2.3</td>
      <td headers="h-quarter h-q1 h-q1t">2.5</td>
      <td headers="h-quarter h-q2 h-q2a">2.7</td>
      <td headers="h-quarter h-q2 h-q2t">2.9</td>
      <td headers="h-h1 h-h1a">5.0</td>
      <td headers="h-h1 h-h1t">5.4</td>
      <td headers="h-var">−0.4</td>
      <td headers="h-notes">Marketing pullback.</td>
    </tr>
    <tr>
      <!-- APAC subtotal row uses colspan to merge the Product + Q1/Q2 cells into a label -->
      <th scope="row" colspan="5">APAC Subtotal (Alpha + Beta)</th>
      <td headers="h-h1 h-h1a">12.4</td>
      <td headers="h-h1 h-h1t">12.2</td>
      <td headers="h-var">+0.2</td>
      <td headers="h-notes">Subtotal row merges cells.</td>
    </tr>
  </tbody>

  <tfoot>
    <tr>
      <!-- Footer total merges Region + Product into one label cell -->
      <th scope="row" colspan="2">Grand Total</th>
      <td colspan="4">—</td>
      <td headers="h-h1 h-h1a"><strong>29.3</strong></td>
      <td headers="h-h1 h-h1t"><strong>28.6</strong></td>
      <td headers="h-var"><strong>+0.7</strong></td>
      <td headers="h-notes">Footer with merged label cells.</td>
    </tr>
  </tfoot>
</table>
