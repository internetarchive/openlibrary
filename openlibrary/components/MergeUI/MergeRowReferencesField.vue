<template>
    <div v-if="record.type.key === '/type/work' && (!merged || (merged && record != merged.record))">
        <div class="list-counts">
            <span v-if="!lists">⏳ lists</span>
            <a v-else-if="lists[record.key].error" :href="`${record.key}/-/lists`" title="Network error: failed to load">⚠️&#xFE0E; lists</a>
            <a v-else :href="`${record.key}/-/lists`">{{lists[record.key].size}} list{{lists[record.key].size == 1 ? '' : 's'}}</a>
        </div>
        <div class="bookshelf-counts">
            RL:
            <span v-if="!bookshelves">⏳ / ⏳ / ⏳</span>
            <span v-else-if="bookshelves[record.key].error" title="Network error: failed to load">⚠️&#xFE0E;</span>
            <span v-else><span v-for="(value, name, index) in bookshelves[record.key].counts" :key="index" :title="name">{{value}}</span></span>
        </div>
        <div class="ratings-counts">
            Ratings:
            <span v-if="!ratings">⏳</span>
            <span v-else-if="ratings[record.key].error" title="Network error: failed to load">⚠️&#xFE0E;</span>
            <span v-else>{{ratings[record.key].summary.count}}</span>
        </div>
    </div>
    <div class="list-counts" v-else-if="merged && record == merged.record && merged.list_count != null">{{merged.list_count}} list{{merged.list_count == 1 ? '' : 's'}}</div>
</template>

<script>

export default {
  props: {
    record: {
      type: Object,
      required: true
    },
    lists: {
      type: Object,
    },
    bookshelves: {
      type: Object,
    },
    ratings: {
      type: Object,
    },
    merged: {
      type: Object,
      required: false
    }
  },
};
</script>
