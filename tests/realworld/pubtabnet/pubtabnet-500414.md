<!-- source: PubTabNet imgid=500414 (https://huggingface.co/datasets/apoidea/pubtabnet-html, CDLA-Permissive-1.0) -->
<table frame="hsides" rules="groups" width="100%">
<thead>
<tr>
<td>
</td>
<td>
<b>
       Matched relations
      </b>
</td>
<td>
<b>
       All relations
      </b>
</td>
<td>
<b>
       Precision
      </b>
</td>
<td>
<b>
       Recall
      </b>
</td>
<td>
<b>
       F measure
      </b>
</td>
<td>
<b>
       Sample size
      </b>
</td>
</tr>
</thead>
<tbody>
<tr>
<td>
      All sentences
     </td>
<td>
      133
     </td>
<td>
      912
     </td>
<td>
      0.14
     </td>
<td>
      1.00 *
     </td>
<td>
      0.24
     </td>
<td>
      451
     </td>
</tr>
<tr>
<td>
      Exclude genes
     </td>
<td>
      110
     </td>
<td>
      660
     </td>
<td>
      0.17
     </td>
<td>
      1.00 *
     </td>
<td>
      0.25
     </td>
<td>
      451
     </td>
</tr>
<tr>
<td>
      Require verbs
     </td>
<td>
      94
     </td>
<td>
      437
     </td>
<td>
      0.21
     </td>
<td>
      1.00 *
     </td>
<td>
      0.34
     </td>
<td>
      451
     </td>
</tr>
<tr>
<td>
      Discovering relations not in MIPS table
     </td>
<td>
      234
     </td>
<td>
      437
     </td>
<td>
      0.53
     </td>
<td>
      1.00 *
     </td>
<td>
      0.69
     </td>
<td>
      451
     </td>
</tr>
<tr>
<td>
      Exclude negatives, alleles
     </td>
<td>
      239
     </td>
<td>
      381
     </td>
<td>
      0.61
     </td>
<td>
      1.00 *
     </td>
<td>
      0.75
     </td>
<td>
      451
     </td>
</tr>
<tr>
<td colspan="7">
<b>
       Including network analysis data
      </b>
</td>
</tr>
<tr>
<td>
      Exclude proteins not part of true relations table.
     </td>
<td>
      239
     </td>
<td>
      343
     </td>
<td>
      0.70
     </td>
<td>
      0.97 *
     </td>
<td>
      0.81
     </td>
<td>
      581
     </td>
</tr>
<tr>
<td>
      Include only validated 2-hop relations
     </td>
<td>
      254
     </td>
<td>
      343
     </td>
<td>
      0.74
     </td>
<td>
      0.97 *
     </td>
<td>
      0.83
     </td>
<td>
      581
     </td>
</tr>
</tbody>
</table>
