<template>
  <div class="tableWrapper">
    <table>
      <thead>
        <tr>
          <th
            rowspan="2"
            style="width:4ch"
          >
            #
          </th>
          <th
            :colspan="columns.length"
            style="width:400px;"
          >
            Extracted Books
          </th>
          <th rowspan="2">
            Matched Books
          </th>
        </tr>
        <tr>
          <th
            v-for="(column, colIndex) in columns"
            :key="colIndex"
          >
            {{ column }}
          </th>
        </tr>
      </thead>
      <tbody>
        <MatchRow
          v-for="bookMatch, index in bulkSearchState.matchedBooks"
          :key="index"
          class="matchRow"
          :book-match="bookMatch"
          :index="index"
          :bulk-search-state="bulkSearchState"
          :columns="columns"
        />
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
    },
    computed: {
        columns(){
            const cols = new Set(
                this.bulkSearchState.matchedBooks
                    .flatMap(bookMatch => Object.keys(bookMatch.extractedBook)
                        .filter(key => bookMatch.extractedBook[key])
                    )
                    .map(col => col.toLowerCase())
            )
            return ['title', 'author', 'isbn'].filter(col => cols.has(col))
        }
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
