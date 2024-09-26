<template>
  <div class="tableWrapper">
    <table>
      <thead>
        <tr>
          <th rowspan ="2" style="width:4ch">#</th>
          <th colspan = "2" style="width:400px;"> Extracted Books</th>
          <th rowspan = "2">Matched Books</th>
        </tr>
        <tr>
          <th>Title</th>
          <th style="min-width: 200px;"> Author</th>
        </tr>
      </thead>
      <tbody>
        <MatchRow class="matchRow" v-for="bookMatch, index  in bulkSearchState.matchedBooks" :bookMatch="bookMatch" :index="index"
          :bulkSearchState="bulkSearchState" :key="index" />
      </tbody>
    </table>
  </div>
</template>

<script>
import MatchRow from './MatchRow.vue'
import { BulkSearchState } from '../utils/classes.js'
export default {
    components: {
        MatchRow
    },
    props: {
        bulkSearchState: BulkSearchState,
    }
}</script>

<style>
table {
  border-collapse:separate;
  width:100%;
  max-width:100vw;
  table-layout:fixed;
  border-spacing:0px 2px;
  padding: 20px;
}
tr:first-child>th:first-child, td:first-child{
  border-radius: 5px 0px 0px 5px;
}

tr:first-child>th:last-child, td:last-child{
  border-radius: 0px 5px 5px 0px
}

th{
  background-color:#C4C4C4;
  outline:2px solid #C4C4C4;
}

thead{
    transform: translate(0px,-2px);
}

.matchRow td{
  background-color: #EEEEEE;
}
.matchRow>td{
  padding: 0.5rem 0.5rem;
  text-align:left;
}
.matchRow:nth-child(odd) td{
  background-color: #E4E4E4;
  margin:2px;
}
.tableWrapper {
  max-width: 100%;
  overflow-x: auto;
}
</style>
