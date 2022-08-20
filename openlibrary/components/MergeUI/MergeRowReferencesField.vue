<template>
    <div v-if="record.type.key === '/type/work' && (!merged || (merged && record != merged.record))">
        <div class="list-counts" v-if="lists">
        <a :href="`${record.key}/-/lists`">{{lists[record.key].size}} list{{lists[record.key].size == 1 ? '' : 's'}}</a>
        </div>
        <div v-else>⏳</div>
        <div class="bookshelf-counts" v-if="bookshelves">
        RL: <span v-for="(value, name, index) in bookshelves[record.key]" :key="index" :title="name">
            {{value}}
        </span>
        </div>
        <div v-else>RL: ⏳ / ⏳ / ⏳</div>

        <div>
        Ratings:
            <span v-if="ratings">{{ratings[record.key].summary.count}}</span>
            <span v-else>⏳</span>
        </div>
    </div>
    <div class="list-counts" v-else-if="merged && record == merged.record">{{merged.list_count}} list{{merged.list_count == 1 ? '' : 's'}}</div>
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
