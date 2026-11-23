<template>
    <div class="ol-bulk-search">
        <BulkSearchControls :bulk-search-state="bulkSearchState" :strings="strings" />
        <hr />
        <MatchTable v-if="bulkSearchState.matchedBooks.length" :bulk-search-state="bulkSearchState" :strings="strings" :list-url="bulkSearchState.listUrl" />
    </div>
</template>

<script>
import BulkSearchControls from './BulkSearch/components/BulkSearchControls.vue';
import { BulkSearchState } from './BulkSearch/utils/classes.js';
import MatchTable from './BulkSearch/components/MatchTable.vue';
import { bulkSearchStringsFromAttr } from './BulkSearch/utils/i18n.js';
export default {
    components: {
        BulkSearchControls,
        MatchTable
    },
    props: {
        /** URI-encoded JSON of translated UI strings; see bulk_search.html.jinja. */
        i18n: {
            type: String,
            default: ''
        }
    },
    data() {
        const strings = bulkSearchStringsFromAttr(this.i18n);
        return {
            strings,
            bulkSearchState: new BulkSearchState(strings)
        };
    }
};
</script>

<style>
.ol-bulk-search {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji';
}

button,
select,
input {
    font-family: inherit;
}
button,
textarea {
    font-size: inherit;
}
select,
input,
textarea {
    padding: 6px;
}
</style>
