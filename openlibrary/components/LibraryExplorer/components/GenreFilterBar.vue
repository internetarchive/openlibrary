<template>
  <div
    v-if="ready"
    class="genre-filter-bar"
  >
    <ol-toggle
      label="Readable Only"
      variant="card"
      :checked="filterState.has_ebook === 'true'"
      @ol-toggle-change="filterState.has_ebook = $event.detail.checked ? 'true' : ''"
    />

    <ol-select-popover
      label="Language"
      placeholder="Filter languages…"
      unselected-heading="LANGUAGES"
      :items="languageItems"
      :selected="languageSelected"
      @ol-select-popover-change="onLanguageChange"
    />

    <ol-options-popover
      label="Audience"
      :items="audienceItems"
      :selected="filterState.age"
      @ol-options-popover-change="filterState.age = $event.detail.selected"
    />

    <ol-options-popover
      label="Fiction"
      :items="fictionItems"
      :selected="filterState.fiction"
      @ol-options-popover-change="filterState.fiction = $event.detail.selected"
    />

    <ol-select-popover
      label="Tags"
      placeholder="Filter subjects…"
      unselected-heading="SUBJECTS"
      :items="tagItems"
      :selected="filterState.tags"
      @ol-select-popover-change="filterState.tags = $event.detail.selected"
    />

    <ol-options-popover
      label="Length"
      :items="lengthItems"
      :selected="filterState.length"
      @ol-options-popover-change="filterState.length = $event.detail.selected"
    />

    <ol-options-popover
      label="Sort"
      :items="sortItems"
      :selected="sortState.order"
      @ol-options-popover-change="sortState.order = $event.detail.selected"
    />
  </div>
</template>

<script>
import GENRE from '../genre.json';
import CONFIGS from '../../configs';

const AUDIENCE_ITEMS = [
    { value: '', label: 'Any' },
    { value: 'juvenile', label: 'Juvenile' },
];

// subject_key values, not display names -- verified live against production
// (subject_key:fiction / subject_key:nonfiction both return well-populated results).
const FICTION_ITEMS = [
    { value: '', label: 'Any' },
    { value: 'fiction', label: 'Fiction' },
    { value: 'nonfiction', label: 'Nonfiction' },
];

// Keys here must match PAGE_LENGTH_RANGES in LibraryExplorer.vue -- kept as separate,
// independent constants (rather than one shared module) since the two files serve very
// different concerns (Solr range strings vs. UI labels) and this list won't change often.
const LENGTH_ITEMS = [
    { value: '', label: 'Any Length' },
    { value: 'micro', label: 'Micro (< 30 pages)' },
    { value: 'short', label: 'Short (30–49 pages)' },
    { value: 'medium', label: 'Medium (50–174 pages)' },
    { value: 'long', label: 'Long (175–499 pages)' },
    { value: 'massive', label: 'Massive (500+ pages)' },
];

// "Dewey Decimal" order (BookRoom/LibraryToolbar's "Shelf Order") is deliberately not
// offered here -- genre/subgenre has no orderable Solr field the way ddc_sort/lcc_sort
// do (see supportsPreciseJump: false on the Genre ClassificationTree in
// LibraryExplorer.vue), so there's nothing for it to sort by.
const SORT_ITEMS = [
    { value: 'trending', label: 'Trending' },
    { value: 'new', label: 'Year (Newest)' },
    { value: 'old', label: 'Year (Oldest)' },
    { value: 'rating', label: 'Star Ratings' },
];

// Every genre and subgenre name, for the Tags picker -- deduped by slug (a subgenre like
// Apocalyptic appears once here even though it's nested under multiple parent genres).
const TAG_ITEMS = (() => {
    const bySlug = new Map();
    for (const genre of GENRE) {
        bySlug.set(genre.short, genre.name);
        for (const subgenre of genre.children || []) {
            bySlug.set(subgenre.short, subgenre.name);
        }
    }
    return [...bySlug].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
})();

export default {
    props: {
        filterState: Object,
        sortState: Object,
    },
    data() {
        return {
            // This component's own script (loaded mid-page, via LibraryExplorer's own
            // <script type="module">) runs BEFORE the site-wide Lit bundle in the page
            // footer that defines ol-toggle/ol-select-popover/ol-options-popover. If Vue
            // patches e.g. :items on one of these tags before it's upgraded, its
            // property doesn't exist yet ("items" in el is false), so Vue's custom-element
            // handling falls back to setAttribute -- which stringifies the array into
            // garbage Lit can't parse back out. Gating the whole bar behind
            // customElements.whenDefined avoids ever patching props into an unupgraded
            // element.
            ready: false,
            languageOptions: [],
            audienceItems: AUDIENCE_ITEMS,
            fictionItems: FICTION_ITEMS,
            lengthItems: LENGTH_ITEMS,
            sortItems: SORT_ITEMS,
            tagItems: TAG_ITEMS,
        };
    },
    computed: {
        // ol-select-popover works in flat value strings; filterState.languages is
        // {name, key} objects (an existing shape LibraryToolbar.vue's own language
        // picker also reads/writes, so kept as-is rather than changed here).
        languageItems() {
            return this.languageOptions.map(lang => ({ value: lang.key, label: lang.name }));
        },
        languageSelected() {
            return this.filterState.languages.map(lang => lang.key);
        },
    },
    async mounted() {
        // Also wait out the languages fetch here (rather than firing-and-forgetting it in
        // created()) so the Language popover's real item list -- not a still-empty one --
        // is what's measured the first time it opens. ol-popover computes its position
        // exactly once, at open, from the panel's rendered height; measuring an empty list
        // and then having ~180 languages' worth of content pop in after can result in the
        // wrong up/down flip decision.
        //
        // Caught independently of the whenDefined waits below: fetch() doesn't reject on
        // an HTTP error status (only on a network-level failure), but .json() throws if
        // the response body isn't valid JSON (e.g. a proxy/gateway error page) -- and an
        // uncaught rejection anywhere in this Promise.all would fail the whole thing,
        // permanently leaving `ready` false and silently hiding the *entire* bar over a
        // Language-only failure. Language just falls back to an empty list instead.
        const params = CONFIGS.LANG ? `?lang=${CONFIGS.LANG}` : '';
        const languagesPromise = fetch(`${CONFIGS.OL_BASE_LANGS}/languages.json${params}`)
            .then(r => r.json())
            .catch(() => []);
        const [languageOptions] = await Promise.all([
            languagesPromise,
            ...['ol-toggle', 'ol-select-popover', 'ol-options-popover'].map(tag => customElements.whenDefined(tag)),
        ]);
        this.languageOptions = languageOptions;
        this.ready = true;
    },
    methods: {
        onLanguageChange(e) {
            const selectedKeys = new Set(e.detail.selected);
            this.filterState.languages = this.languageOptions.filter(lang => selectedKeys.has(lang.key));
        },
    },
};
</script>

<style scoped>
.genre-filter-bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 24px;
}
</style>
