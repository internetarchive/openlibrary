<template>
  <div
    id="app"
    role="main"
  >
    <BookRoom
      :classification="settingsState.selectedClassification"
      :filter="computedFilter"
      :sort="sortState.order"
      :class="bookRoomClass"
      :features="bookRoomFeatures"
      :app-settings="settingsState"
      :jump-to="jumpTo"
    />

    <LibraryToolbar
      :filter-state="filterState"
      :settings-state="settingsState"
      :sort-state="sortState"
    />
  </div>
</template>

<script>
import BookRoom from './LibraryExplorer/components/BookRoom.vue';
import LibraryToolbar from './LibraryExplorer/components/LibraryToolbar.vue';
import DDC from './LibraryExplorer/ddc.json';
import LCC from './LibraryExplorer/lcc.json';
import { recurForEach } from './LibraryExplorer/utils.js';
import { sortable_lcc_to_short_lcc, short_lcc_to_sortable_lcc } from './LibraryExplorer/utils/lcc.js';
import maxBy from 'lodash/maxBy';

class FilterState {
    constructor() {
        this.filter = '';
        /** @type {boolean} */
        this.has_ebook = true;
        this.languages = [];
        this.age = '';
        // Use '*' as upper bound for Solr range
        this.year = '[1985 TO *]';
    }

    solrQueryParts() {
        const filters = this.filter ? [this.filter] : [];

        if (this.has_ebook !== null) {
            filters.push(`has_fulltext:${this.has_ebook ? 'true' : 'false'}`);
        }

        if (this.languages.length) {
            const langs = this.languages
                .map(lang => lang.key?.split('/')[2])
                .filter(Boolean);
            if (langs.length) {
                filters.push(`language:(${langs.join(' OR ')})`);
            }
        }

        if (this.age) {
            filters.push(`subject:${this.age}`);
        }

        if (this.year) {
            filters.push(`first_publish_year:${this.year}`);
        }

        return filters;
    }

    solrQuery() {
        return this.solrQueryParts().join(' AND ');
    }
}

export default {
    components: {
        BookRoom,
        LibraryToolbar,
    },

    data() {
        const classifications = [
            {
                name: 'DDC',
                longName: 'Dewey Decimal Classification',
                field: 'ddc',
                fieldTransform: ddc => ddc,
                toQueryFormat: ddc => ddc,
                chooseBest: ddcs =>
                    maxBy(ddcs, ddc =>
                        ddc.replace(/[\d.]/g, '') ? ddc.length : 100 + ddc.length
                    ),
                root: recurForEach({ children: DDC, query: '*' }, n => {
                    n.position = 'root';
                    n.offset = 0;
                    n.requests = {};
                })
            },
            {
                name: 'LCC',
                longName: 'Library of Congress Classification',
                field: 'lcc',
                fieldTransform: sortable_lcc_to_short_lcc,
                toQueryFormat: lcc => {
                    const normalized = short_lcc_to_sortable_lcc(lcc);
                    return normalized ? normalized.split(' ')[0] : lcc;
                },
                chooseBest: lccs => maxBy(lccs, lcc => lcc.length),
                root: recurForEach({ children: LCC, query: '*' }, n => {
                    n.position = 'root';
                    n.offset = 0;
                    n.requests = {};
                })
            }
        ];

        const urlParams = new URLSearchParams(location.search);
        let selectedClassification = classifications[0];
        let jumpTo = null;

        if (urlParams.has('jumpTo')) {
            const [classificationName, classificationString] = urlParams.get('jumpTo').split(':');

            const found = classifications.find(c => c.field === classificationName);
            if (found) {
                selectedClassification = found;
                jumpTo = found.toQueryFormat(classificationString);
            }
        }

        const seed = new Date().toISOString().split(':')[0];

        return {
            filterState: new FilterState(),

            sortState: {
                order: jumpTo
                    ? `${selectedClassification.field}_sort asc`
                    : `random_${seed}`,
            },

            jumpTo,

            settingsState: {
                selectedClassification,
                classifications,

                labels: ['classification'],

                styles: {
                    book: {
                        options: ['default', '3d', 'spines', '3d-spines', '3d-flat'],
                        selected: 'default'
                    },

                    cover: {
                        options: ['image', 'text'],
                        selected: 'image'
                    },

                    shelfLabel: {
                        debugModeOnly: true,
                        options: ['slider', 'expander'],
                        selected: 'slider'
                    },

                    aesthetic: {
                        debugModeOnly: true,
                        options: ['mockup', 'wip'],
                        selected: 'wip'
                    },

                    scrollbar: {
                        options: ['default', 'thin', 'hidden'],
                        selected: 'thin',
                    },
                },
            },
        };
    },

    computed: {
        computedFilter() {
            return this.filterState.solrQuery();
        },

        bookRoomFeatures() {
            return {
                book3d: this.settingsState.styles.book.selected.startsWith('3d'),
                cover: this.settingsState.styles.cover.selected,
                shelfLabel: this.settingsState.styles.shelfLabel.selected
            };
        },

        bookRoomClass() {
            return Object.entries(this.settingsState.styles)
                .map(([key, val]) => `style--${key}--${val.selected}`)
                .join(' ');
        }
    }
};
</script>
