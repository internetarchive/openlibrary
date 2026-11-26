<template>
    <div class="editions-wrapper">
        <div v-if="editions" class="edition-count">{{ editionCount(editions[record.key].size) }}</div>
        <div v-else-if="merged && record == merged.record" class="edition-count">
            {{ editionCount(merged.edition_count) }}
        </div>
        <div v-if="editions" class="td-container">
            <EditionSnippet v-for="edition in editions[record.key].entries" :key="edition.key" :edition="edition" />
        </div>
    </div>
</template>

<script>
import { fmt, ngettext } from '../../plugins/openlibrary/js/i18n.js';
import EditionSnippet from './EditionSnippet.vue';

export default {
    components: {
        EditionSnippet
    },
    props: {
        record: {
            type: Object,
            required: true
        },
        editions: {
            type: Array,
            required: true
        },
        merged: {
            type: Object,
            default: null
        }
    },
    methods: {
        editionCount(count) {
            return fmt(ngettext('%(count)s edition', '%(count)s editions', count), { count });
        }
    }
};
</script>
