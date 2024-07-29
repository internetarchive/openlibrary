<template>
    <tr>
        <td>{{ index + 1 }}</td>
        <td>{{ bookMatch.extractedBook.title }}</td>
        <td>{{ bookMatch.extractedBook.author }}</td>
        <td>
            <div class="bookCards">
                <a :href="searchUrl" title="View results in Open Library">🔎</a>

                <BookCard v-for="(doc, index) in bookMatch.solrDocs.docs" :doc="doc" :key="index" />
            </div>
        </td>
    </tr>
</template>

<script>
import { BulkSearchState, BookMatch } from '../utils/classes.js'
import { buildSearchUrl } from '../utils/searchUtils.js'
import BookCard from './BookCard.vue'
export default {
  components: {
    BookCard
  },
  props: {
    bulkSearchState: BulkSearchState,
    bookMatch: BookMatch,
    index: Number
  },
  computed: {
    searchUrl() {
      return buildSearchUrl(this.bookMatch.extractedBook, this.bulkSearchState.matchOptions, false)
    }
  }
}
</script>

<style>
td,
th {
    border: 1px solid;
    padding: 4px;
}
.bookCards {
    display: flex;
    flex-direction: row;
    align-items: center;


}
</style>
