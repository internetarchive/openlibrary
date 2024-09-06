<template>
  <div class="tableWrapper">
    <table>
      <thead class="tableHead">
        <tr>
          <th style="min-width:75px">i</th>
          <th style="min-width: 200px">Title</th>
          <th style="min-width: 200px">Extracted Books Author</th>
          <th style="width: 100%">Matches</th>
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
  border-spacing:0px 2px;
}
.tableHead{
  background-color:#C4C4C4
}

.matchRow{
  background-color: #EEEEEE;
  margin:2px 2px;
}
.matchRow>td{
  padding: 2rem 0rem;
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
