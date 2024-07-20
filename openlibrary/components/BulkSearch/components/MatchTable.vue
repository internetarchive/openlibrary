<template>
  <div class="tableWrapper">
    <table>
      <thead>
        <tr>
          <th>i</th>
          <th style="min-width: 200px">Title</th>
          <th style="min-width: 200px">Author</th>
          <th style="width: 100%">Matches</th>
        </tr>
      </thead>
      <tbody>
        <MatchRow v-for="bookMatch, index  in bulkSearchState.matchedBooks" :bookMatch="bookMatch" :index="index"
          :bulkSearchState="bulkSearchState" :key="index" />
      </tbody>
      <tfoot>
        <tr>
          <td></td>
          <td></td>
          <td></td>
          <td><a :href="bulkSearchState.listUrl" target="_blank" id="listMakerLink">Create list of first matches</a></td>
        </tr>
      </tfoot>
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
  border-collapse: collapse;
}
.tableWrapper {
  max-width: 100%;
  overflow-x: auto;
}
</style>
