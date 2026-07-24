<template>
  <div id="app">
    <BookRoom
      :classification="settingsState.selectedClassification"
      :filter="computedFilter"
      :sort="sortState.order"
      :class="bookRoomClass"
      :features="bookRoomFeatures"
      :app-settings="settingsState"
      :jump-to="jumpTo"
      :filter-state="filterState"
      :sort-state="sortState"
    />

    <LibraryToolbar
      v-if="!settingsState.selectedClassification.alphabeticalTopNav"
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
import GENRE from './LibraryExplorer/genre.json';
import { recurForEach } from './LibraryExplorer/utils.js';
import { sortable_lcc_to_short_lcc, short_lcc_to_sortable_lcc } from './LibraryExplorer/utils/lcc.js';
import maxBy from 'lodash/maxBy';

// Genre/subgenre slugs, gathered from genre.json, so chooseBest can pick a relevant
// entry out of a book's full (much larger, unrelated) subject_key array.
const GENRE_SLUG_NAMES = new Map();
for (const genre of GENRE) {
    GENRE_SLUG_NAMES.set(genre.short, genre.name);
    for (const subgenre of genre.children || []) {
        GENRE_SLUG_NAMES.set(subgenre.short, subgenre.name);
    }
}
function genreSlugToLabel(slug) {
    return GENRE_SLUG_NAMES.get(slug) || slug;
}

// Verified live against production (openlibrary.org/search.json, number_of_pages_median):
// [0 TO 29]=184, [30 TO 49]=539, [50 TO 174]=3430, [175 TO 499]=6153, [500 TO 100000]=695
// (counts for subject_key:horror* at the time of checking -- real, distinct, non-empty buckets).
export const PAGE_LENGTH_RANGES = {
    micro: '[0 TO 29]',
    short: '[30 TO 49]',
    medium: '[50 TO 174]',
    long: '[175 TO 499]',
    massive: '[500 TO 100000]',
};

class FilterState {
    constructor() {
        this.filter = '';
        /** @type { '' | 'true' | 'false' } */
        this.has_ebook = 'true';
        /** @type {Array<{name: string, key: string}>} */
        this.languages = [];
        this.age = '';
        this.year = '[1985 TO 9998]';
        /** @type {'' | 'fiction' | 'nonfiction'} */
        this.fiction = '';
        /** @type {string[]} subject_key slugs, ANDed together */
        this.tags = [];
        /** @type {'' | keyof typeof PAGE_LENGTH_RANGES} */
        this.length = '';
    }

    solrQueryParts() {
        const filters = this.filter ? [this.filter] : [];
        if (this.has_ebook) {
            filters.push(`has_fulltext:${this.has_ebook}`);
        }

        if (this.languages.length) {
            const langs = this.languages.map(lang => lang.key.split('/')[2]);
            filters.push(`language:(${langs.join(' OR ')})`);
        }
        if (this.age) {
            filters.push(`subject:${this.age}`);
        }
        if (this.fiction) {
            filters.push(`subject_key:${this.fiction}`);
        }
        if (this.year) {
            filters.push(`first_publish_year:${this.year}`);
        }
        for (const tag of this.tags) {
            filters.push(`subject_key:"${tag}"`);
        }
        if (this.length && PAGE_LENGTH_RANGES[this.length]) {
            filters.push(`number_of_pages_median:${PAGE_LENGTH_RANGES[this.length]}`);
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
        /** @type {import('./LibraryExplorer/utils').ClassificationTree[]} */
        const classifications = [
            {
                name: 'DDC',
                longName: 'Dewey Decimal Classification',
                field: 'ddc',
                fieldTransform: ddc => ddc,
                toQueryFormat: ddc => ddc,
                chooseBest: ddcs => maxBy(ddcs, ddc => ddc.replace(/[\d.]/g, '') ? ddc.length : 100 + ddc.length),
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
            },
            {
                name: 'Genre',
                longName: 'Genre & Subgenre',
                field: 'subject_key',
                fieldTransform: genreSlugToLabel,
                toQueryFormat: slug => slug,
                // subject_key holds every subject on a book, not just genre/subgenre tags -- prefer
                // an entry that's actually one of ours, falling back to the raw first value.
                chooseBest: slugs => slugs.find(s => GENRE_SLUG_NAMES.has(s)) || slugs[0],
                // No genre_sort Solr field exists (genre isn't a rankable/orderable classification
                // the way DDC/LCC are), and the top nav is a full alphabetical list, not prev/next.
                supportsPreciseJump: false,
                alphabeticalTopNav: true,
                root: recurForEach({ children: GENRE, query: '*' }, n => {
                    n.position = 'root';
                    n.offset = 0;
                    n.requests = {};
                })
            }
        ];

        const urlParams = new URLSearchParams(location.search);
        let selectedClassification = location.pathname.startsWith('/explore/genres')
            ? classifications.find(c => c.field === 'subject_key')
            : classifications[0];
        let jumpTo = null;
        if (urlParams.has('jumpTo')) {
            const [classificationName, classificationString] = urlParams.get('jumpTo').split(':');
            selectedClassification = classifications.find(c => c.field === classificationName);
            jumpTo = selectedClassification.toQueryFormat(classificationString);
        } else if (location.hash && selectedClassification.alphabeticalTopNav) {
            // #-style anchors (e.g. /explore/genres#fantasy) are genre mode's shorthand for
            // ?jumpTo=subject_key:fantasy -- see BookRoom.vue's hashchange listener for why
            // this exists as its own mechanism instead of just extending the query-param
            // form: a hash is meant to be navigated without a full page reload, which
            // "start at a specific shelf" (e.g. from a homepage genre link) actually wants.
            jumpTo = selectedClassification.toQueryFormat(decodeURIComponent(location.hash.slice(1)));
        }
        return {
            filterState: new FilterState(),

            sortState: {
                order: (jumpTo && selectedClassification.supportsPreciseJump !== false)
                    ? `${selectedClassification.field}_sort asc`
                    : `random_${new Date().toISOString().split(':')[0]}`,
            },

            jumpTo,

            settingsState: {
                selectedClassification,
                classifications,

                labels: ['classification'],

                styles: {
                    book: {
                        options: [
                            'default',
                            '3d',
                            'spines',
                            '3d-spines',
                            '3d-flat'
                        ],
                        selected: 'default'
                    },

                    cover: {
                        options: [
                            'image',
                            'text'
                        ],
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

<style>
#app {
  font-family: "Avenir", Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: rgba(0, 0, 0, .7);
}

details[open] summary ~ * {
  animation: sweep .2s;
}

@keyframes sweep {
  0% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
}

.class-slider {
  margin-bottom: 5px;
}

hr {
  width: 100%;
}

.book-room .class-slider .sections {
  background: rgba(255, 255, 255, .3);
  --highlight-color: rgba(255, 255, 255, .5);
  border-radius: 4px;
  height: 4px;
}

.book-room .book-end-start {
  display: none;
}

.book-room .book {
  position: relative;
  margin-left: 10px;
}
.book-room .book-end-wrapper + .book { margin-left: 20px; }

.book-room .cover-label {
  background: rgba(0, 0, 0, .5);
  position: absolute;
  bottom: 0;
  font-size: .8em;
  opacity: .9;
  line-height: .8em;
}

.book-room.style--book--spines .book {
  animation: 200ms slide-in;
  transition: width .2s;
  transition-delay: .5s;
  width: 40px;
  margin: 0;
  overflow: hidden;
  overflow: clip;
  flex-shrink: 0;
  margin-left: 1px;
}

.book-room.style--book--spines .book img {
  width: 150px;
  margin-left: -40px;
  object-fit: cover;
  object-position: center;
  transition: margin-left .2s;
  transition-delay: .5s;
}
.book-room.style--book--spines .book:hover img {
  margin-left: 0;
}
.book-room.style--book--spines .book:hover {
  width: 150px;
}

.book-room.style--book--3d .cover,
.book-room.style--book--3d-spines .cover,
.book-room.style--book--3d-flat .cover {
  opacity: .8;
  transition: opacity .2s;
}
.book-room.style--book--3d .book-end-wrapper + .book,
.book-room.style--book--3d-spines .book-end-wrapper + .book,
.book-room.style--book--3d-flat .book-end-wrapper + .book {
  margin-left: 60px;
}
.book-room.style--book--3d .book:hover .cover,
.book-room.style--book--3d-spines .book:hover .cover,
.book-room.style--book--3d-flat .book:hover .cover {
  opacity: 1;
}
.book-room.style--book--3d .book:hover .book-3d.css-box,
.book-room.style--book--3d-spines .book:hover .book-3d.css-box,
.book-room.style--book--3d-flat .book:hover .book-3d.css-box {
  backface-visibility: hidden;
  transform: perspective(2000px) translate3d(-40px, 0, 100px) rotateY(-15deg);
}
.book-room.style--book--3d .css-box,
.book-room.style--book--3d .css-box > *,
.book-room.style--book--3d-spines .css-box,
.book-room.style--book--3d-spines .css-box > *,
.book-room.style--book--3d-flat .css-box,
.book-room.style--book--3d-flat .css-box > * {
  transition-duration: .2s;
  transition-property: width, height, transform;
}

.book-room.style--book--3d-spines .book {
  margin-left: -100px;
}
.book-room.style--book--3d-spines .book:hover {
  z-index: 1;
}

.book-room.style--book--3d-flat .css-box {
  transform: unset !important;
}
.book-room.style--book--3d-flat .book {
  transform: rotateX(20deg);
  transform-style: preserve-3d;
  margin-left: 18px;
}
.book-room.style--book--3d-flat .book-end-wrapper + .book {
  margin-left: 40px;
}
.book-room.style--book--3d-flat .books-carousel {
  perspective: 2000px;
}

#app {
  font-family: "bahnschrift", -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol";
}

.book-room.style--aesthetic--wip {
  background: linear-gradient(180deg,#ebdfc5 100px, #dbbe9f 1600px,#cba37e 4800px);
  background-position: scroll;
}
.book-room.style--aesthetic--wip .classification-short {
  opacity: .6;
}
.book-room.style--aesthetic--wip .bookshelf-wrapper {
  margin-left: 140px;
}
.book-room.style--aesthetic--wip .bookshelf {
  background: linear-gradient(
    to right,
    rgba(29, 5, 0, .5),
    rgba(61, 0, 0, .1) 20%,
    transparent,
    rgba(61, 0, 0, .1) 60%,
    rgba(29, 5, 0, .5)
  ),
    linear-gradient(
    to bottom,
    transparent 0,
    transparent 10px,
    rgba(255, 191, 0, .4) 10px,
    rgba(255, 191, 0, .1) 15px,
    transparent 50px
  ),
    linear-gradient(
    to bottom,
    #543721 0,
    #5a3b23 10px,
    #7b5130 10px,
    #5f432d
  );
  border: 0;
  padding: 36px 0 10px;
  box-sizing: border-box;
  color: white;
}
.book-room.style--aesthetic--wip .bookshelf-name button {
  background: none;
  border: none;
  color: inherit;
  padding: 6px 8px;
  transition: background-color 0.2s;
  cursor: pointer;
}
.book-room.style--aesthetic--wip .bookshelf-name button:hover {
  background: rgba(255, 255, 255, .1);
}
.book-room.style--aesthetic--wip .shelf {
  margin-bottom: 35px;
}
.book-room.style--aesthetic--wip .shelf .shelf-index {
  padding: 4px 8px;
  opacity: 0.95;
}
.book-room.style--aesthetic--wip .shelf .shelf-index a {
  border-radius: 4px;
  border: 1px solid transparent;
  line-height: 0.9em;
}
.book-room.style--aesthetic--wip .shelf .shelf-index .selected {
  background: rgba(255,255,255, 0.1);
  border: 1px solid white;
  border-left-width: 4px;
  color: inherit;
}
.book-room.style--aesthetic--wip .shelf .shelf-index .shelf-label--subclasses--count {
  font-size: 0.8em;
  font-weight: 300;
  opacity: 0.8;
}
.book-room.style--aesthetic--wip .shelf .shelf-index .shelf-label--subclasses--count::before {
  content: "• ";
}
.book-room.style--aesthetic--wip .shelf-carousel {
  border: 0;
  margin: 0;
  background-color: #563822;
  background-image: linear-gradient(
    to bottom,
    rgba(0, 0, 0, .36),
    #563822 50px
  );
}
.book-room.style--aesthetic--wip .class-slider.shelf-label {
  border: 0;
  background: none;
  color: rgba(255, 255, 255, .9);
  font-weight: 400;
  margin: 0;
  min-height: 2em;
}
.book-room.style--aesthetic--wip .shelf-label {
  background: none;
}
.book-room.style--aesthetic--wip .shelf-label button {
  border: 0;
  border-radius: 4px;
  transition: background-color .2s;
  cursor: pointer;
}
.book-room.style--aesthetic--wip .shelf-label button.selected {
  border: 1px solid white;
  background-color: rgba(255, 255, 255, .3);
}
.book-room.style--aesthetic--wip .shelf-label button:hover {
  background-color: rgba(255, 255, 255, .2);
}
.book-room.style--aesthetic--wip .shelf-label .sections {
  height: 4px;
  bottom: 0;
}

.book-room.style--scrollbar--thin .books-carousel {
  scrollbar-width: thin;
}
/* Chrome-specific scroll fixes */
.book-room.style--scrollbar--thin .books-carousel::-webkit-scrollbar { height: 6px; }
.book-room.style--scrollbar--thin .books-carousel::-webkit-scrollbar-thumb { background: rgba(255,255,255, 0.35); }
.book-room.style--scrollbar--thin .books-carousel::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255, 0.25); }
.book-room.style--scrollbar--thin .books-carousel::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.2); }

.book-room.style--scrollbar--hidden .books-carousel { scrollbar-width: none; }
.book-room.style--scrollbar--hidden .books-carousel::-webkit-scrollbar { height: 0; }
</style>
