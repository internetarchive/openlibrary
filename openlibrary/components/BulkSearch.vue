<template>
    <div>
        <BulkSearchControls :bulkSearchState="bulkSearchState" />
        <hr />
        <MatchTable v-if="bulkSearchState.matchedBooks.length" :bulkSearchState="bulkSearchState"  :listUrl = bulkSearchState.listUrl />
    </div>
</template>


<script>
import BulkSearchControls from './BulkSearch/components/BulkSearchControls.vue'
import { BulkSearchState } from './BulkSearch/utils/classes.js';
import MatchTable from './BulkSearch/components/MatchTable.vue';
export default {
  components: {
    BulkSearchControls, MatchTable
  },
  data() {
    return {
      bulkSearchState: new BulkSearchState()
    }
  }
}
</script>
