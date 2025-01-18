<template>
  <div class="ol-bulk-search">
    <BulkSearchControls :bulk-search-state="bulkSearchState" />
    <hr>
    <MatchTable
      v-if="bulkSearchState.matchedBooks.length"
      :bulk-search-state="bulkSearchState"
      :list-url="bulkSearchState.listUrl"
    />
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

<style>
.ol-bulk-search{
    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji";
}

button, select, input{
    font-family:inherit;
}
button, textarea{
    font-size:inherit;
}
select, input, textarea{
    padding:6px;
}
</style>
