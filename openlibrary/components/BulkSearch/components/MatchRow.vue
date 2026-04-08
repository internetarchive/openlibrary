<template>
  <tr>
    <td>{{ index + 1 }}</td>
    <td
      v-for="(column, colIndex) in columns"
      :key="colIndex"
    >
      {{ bookMatch.extractedBook[column] || '' }}
    </td>
    <td>
      <div class="bookCards">
        <a
          :href="searchUrl"
          title="View results in Open Library"
        >🔎</a>
        <BookCard
          v-for="(doc, index) in bookMatch.solrDocs.docs"
          :key="index"
          :doc="doc"
          :is-primary="index === 0"
        />
        <NoBookCard v-if="bookMatch.solrDocs.numFound===0" />
      </div>
    </td>
  </tr>
</template>

<script>
import { BulkSearchState, BookMatch } from '../utils/classes.js'
import { buildSearchUrl } from '../utils/searchUtils.js'
import BookCard from './BookCard.vue'
import NoBookCard from './NoBookCard.vue'
export default {
    components: {
        BookCard, NoBookCard
    },
    props: {
        bulkSearchState: BulkSearchState,
        bookMatch: BookMatch,
        columns: Array,
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
    padding: 5px;
    text-align:center;
}
.bookCards {
    display: flex;
    flex-direction: row;
    align-items: center;
    overflow-x:auto;
    scrollbar-width:thin;

    .book-card--primary {
        margin-right: 20px;
    }
}


</style>
