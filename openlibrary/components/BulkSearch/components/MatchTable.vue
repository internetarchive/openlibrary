<template>
  <div class="tableWrapper">
    <table>
      <thead class="tableHead">
        <tr>
          <th rowspan ="2" style="width:75px">#</th>
          <th colspan = "2" style="width:400px;"> Extracted Books</th>
          <th rowspan = "2" style="">Matched Books</th>
        </tr>
        <tr>
          <th>Title</th>
          <th style="min-width: 200px; margin-top:0px;"> Author</th>
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
  border-collapse: separate;
  width:100%;
  max-width:100vw;
  table-layout:fixed;
  border-spacing:0px 2px;
}
.tableHead{
  background-color:#C4C4C4;
}

.matchRow{
  background-color: #EEEEEE;
}
.matchRow>td{
  padding: 0.5rem 0.5rem;
  text-align:left;
}
.matchRow:nth-child(odd){
  background-color: #E4E4E4;
  margin:2px;
}
.tableWrapper {
  max-width: 100%;
  overflow-x: auto;
}
</style>
