<template>
    <ul class="reset">
        <li v-for="(excerpt, index) in excerpts" :key="index" class="excerpt-item">
            <span v-if="excerpt['excerpt']" :title="`excerpt-${index}`">
                {{ excerpt['excerpt'].value || excerpt['excerpt'] }}
            </span>
            <span v-if="excerpt['pages']"> {{ pageLabel(excerpt['pages']) }} </span>
            <span v-if="excerpt['page']"> {{ pageLabel(excerpt['page']) }} </span>
            <span v-if="excerpt['author']">
                <a :href="excerpt['author'].key" target="_blank">
                    {{ excerpt['author'].key.slice('/people/'.length) }}
                </a>
            </span>
        </li>
    </ul>
</template>

<script>
import { _, fmt } from '../../plugins/openlibrary/js/i18n.js';

export default {
    props: {
        excerpts: {
            type: Array,
            default: () => []
        }
    },
    computed: {
        fields() {
            return [...new Set(this.excerpts.flatMap(excerpt => Object.keys(excerpt)))];
        }
    },
    methods: {
        pageLabel(page) {
            return fmt(_('(page: %(page)s)'), { page });
        }
    }
};
</script>
