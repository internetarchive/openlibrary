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

    <ol-toggle
      label="Enrich"
      variant="card"
      :checked="genreEnriched"
      accessible-label="Enrich genres/subgenres with demo data on top of the raw tags vocabulary"
      @ol-toggle-change="$emit('update:genre-enriched', $event.detail.checked)"
    />
  </div>

  <!-- Selected-filter pills, mirroring work_search_selected_facets.html's convention: only
       for controls whose own trigger doesn't already surface the selection. Readable Only
       shows its state via the toggle switch itself, and Language via its own popover
       trigger label -- both skipped here to avoid a redundant chip.

       Teleported to .genre-sticky-header (passed down from BookRoom.vue as an actual
       element, not a selector -- simpler than resolving a selector across the shadow
       root) rather than rendered inline here: the pills sit on the bookcase's own top
       board, not inside the hanging sign, so they need to be a sibling of .genre-top-board
       in the DOM, not a descendant of .genre-filter-bar. -->
  <Teleport
    v-if="ready && chipsTeleportTarget && activeChips.length"
    :to="chipsTeleportTarget"
  >
    <ol-chip-group class="genre-filter-bar__chips">
      <ol-chip
        v-for="chip of activeChips"
        :key="chip.key"
        selected
        size="small"
        :variant="chip.variant"
        @ol-chip-select="chip.clear"
      >
        {{ chip.label }}
      </ol-chip>
    </ol-chip-group>
  </Teleport>
</template>

<script>
import { nextTick } from 'vue';
import GENRE from '../genre.json';
import CONFIGS from '../../configs';

// filterState.age plugs into `subject:${age}` (LibraryExplorer.vue) for every value except
// 'adult' -- there's no dedicated audience field in Solr (confirmed: home/index.html's own
// genre carousel works around the same gap by hand-building an OR of subject_key values
// instead), and no real "adult" subject to positively match against either (subject:adult
// returns a healthy count, but ~1/3 of it is "Young Adult" books). 'adult' is special-cased
// to -subject:juvenile instead, which is what the label actually means here.
const AUDIENCE_ITEMS = [
    { value: '', label: 'Any' },
    { value: 'juvenile', label: 'Juvenile' },
    { value: 'adult', label: 'Adult' },
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
        genreEnriched: Boolean,
        // The actual .genre-sticky-header element (not a CSS selector -- avoids resolving
        // one across the shadow root) that the selected-filter pills teleport to. null
        // until BookRoom.vue's own mounted() resolves its template ref.
        chipsTeleportTarget: Object,
        // Language keys (e.g. "/languages/eng") pulled from a shared ?language= URL param
        // by LibraryExplorer.vue's data(). Every other URL-shareable filter is a plain
        // string filterState/sortState already holds directly, so LibraryExplorer.vue
        // applies those itself -- language is the one exception, since filterState.languages
        // needs each key resolved to a {name, key} object off the language list this
        // component fetches asynchronously below, which LibraryExplorer.vue has no access to.
        initialLanguageKeys: {
            type: Array,
            default: () => [],
        },
    },
    emits: ['ready', 'update:genre-enriched'],
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

        activeChips() {
            const chips = [];
            // AUDIENCE_ITEMS/FICTION_ITEMS/LENGTH_ITEMS all include an explicit `value: ''`
            // "Any" entry (the unset default) -- skip empty values up front rather than
            // relying on "no item matches", since '' matching that entry is exactly the
            // no-selection case we don't want a chip for.
            const addFromItems = (key, items, value, clear) => {
                if (!value) return;
                const item = items.find(it => it.value === value);
                if (item) chips.push({ key, label: item.label, clear });
            };

            addFromItems('age', AUDIENCE_ITEMS, this.filterState.age, () => { this.filterState.age = ''; });
            addFromItems('fiction', FICTION_ITEMS, this.filterState.fiction, () => { this.filterState.fiction = ''; });
            for (const tag of this.filterState.tags) {
                addFromItems(`tag-${tag}`, TAG_ITEMS, tag, () => {
                    this.filterState.tags = this.filterState.tags.filter(t => t !== tag);
                });
            }
            addFromItems('length', LENGTH_ITEMS, this.filterState.length, () => { this.filterState.length = ''; });
            // sortState.order defaults to a random_* string with no matching SORT_ITEM
            // (see LibraryExplorer.vue), so this naturally shows nothing until the user
            // picks an explicit option.
            addFromItems('sort', SORT_ITEMS, this.sortState.order, () => { this.sortState.order = SORT_ITEMS[0].value; });

            return chips;
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
        if (this.initialLanguageKeys.length && !this.filterState.languages.length) {
            const keys = new Set(this.initialLanguageKeys);
            this.filterState.languages = this.languageOptions.filter(lang => keys.has(lang.key));
        }
        this.ready = true;
        // BookRoom's --genre-nav-height (which .shelf's scroll-margin-top reads to clear
        // the sticky header) is measured once at mount, before this bar exists at all --
        // let it know to re-measure once this actually renders and takes up real height.
        await nextTick();
        this.$emit('ready');
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

/* flex-basis: 100% forces this onto its own row below the controls above, rather than
   wrapping in wherever there happens to be leftover space on their last line. */
.genre-filter-bar__chips {
  flex-basis: 100%;
  justify-content: center;
  margin-top: 4px;
}
</style>
