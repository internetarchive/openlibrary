<template>
    <div v-if="record.type.key === '/type/work' && (!merged || (merged && record != merged.record))">
        <div class="list-counts">
            <span v-if="!lists">⏳ {{ strings.lists }}</span>
            <a v-else-if="lists[record.key].error" :href="`${record.key}/-/lists`" :title="strings.networkError">⚠️&#xFE0E; {{ strings.lists }}</a>
            <a v-else :href="`${record.key}/-/lists`">{{ listCount(lists[record.key].size) }}</a>
        </div>
        <div class="bookshelf-counts">
            {{ strings.readingLog }}
            <span v-if="!bookshelves">⏳ / ⏳ / ⏳</span>
            <span v-else-if="bookshelves[record.key].error" :title="strings.networkError">⚠️&#xFE0E;</span>
            <span v-else
                ><span v-for="(value, name, index) in bookshelves[record.key].counts" :key="index" :title="name">{{ value }}</span></span
            >
        </div>
        <div class="ratings-counts">
            {{ strings.ratings }}
            <span v-if="!ratings">⏳</span>
            <span v-else-if="ratings[record.key].error" :title="strings.networkError">⚠️&#xFE0E;</span>
            <span v-else>{{ ratings[record.key].summary.count }}</span>
        </div>
    </div>
    <div v-else-if="merged && record == merged.record && merged.list_count != null" class="list-counts">
        {{ listCount(merged.list_count) }}
    </div>
</template>

<script>
import { _, fmt, ngettext } from '../../plugins/openlibrary/js/i18n.js';

export default {
    props: {
        record: {
            type: Object,
            required: true
        },
        lists: {
            type: Object,
            default: null
        },
        bookshelves: {
            type: Object,
            default: null
        },
        ratings: {
            type: Object,
            default: null
        },
        merged: {
            type: Object,
            default: null
        }
    },
    data() {
        return {
            strings: {
                // NOTE: Shown after a loading or warning icon, in place of the number of lists the work is on.
                lists: _('lists'),
                // NOTE: Abbreviation of "Reading Log"; followed by the counts of readers who want to read, are reading and have read the work.
                readingLog: _('RL:'),
                // NOTE: Label for the number of ratings the work has.
                ratings: _('Ratings:'),
                networkError: _('Network error: failed to load')
            }
        };
    },
    methods: {
        listCount(count) {
            return fmt(ngettext('%(count)s list', '%(count)s lists', count), { count });
        }
    }
};
</script>
