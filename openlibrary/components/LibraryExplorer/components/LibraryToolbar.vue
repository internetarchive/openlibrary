<template>
    <div class="floating-controls-wrapper">
      <div class="floating-controls" :class="{open: openTabs.length > 0}">
        <div class="tab-bar">
          <button class="chunky-icon tab-bar--tab" v-if="openTabs.length" @click="openTabs.splice(0, openTabs.length)">
            <div class="chunky-icon--icon" style="font-size: 32px; font-weight: 100; line-height: 28px;">
              &times;
            </div>
            <div class="chunky-icon--label">
              Close
            </div>
          </button>
          <button class="chunky-icon tab-bar--tab" :class="{active: openTabs.includes('filter')}" @click="toggleTab('filter')">
            <div class="chunky-icon--icon">
              <FilterIcon/>
            </div>
            <div class="chunky-icon--label">
              Filter
              <span style="opacity: .55" v-if="activeFiltersCount">({{activeFiltersCount}})</span>
            </div>
          </button>
          <button class="chunky-icon tab-bar--tab" :class="{active: openTabs.includes('sort')}" @click="toggleTab('sort')">
            <div class="chunky-icon--icon">
              <SortIcon/>
            </div>
            <div class="chunky-icon--label">Sort</div>
          </button>
          <button class="chunky-icon tab-bar--tab" :class="{active: openTabs.includes('settings')}" @click="toggleTab('settings')">
            <div class="chunky-icon--icon">
              <SettingsIcon/>
            </div>
            <div class="chunky-icon--label">Settings</div>
          </button>
          <button class="chunky-icon tab-bar--tab" :class="{active: openTabs.includes('feedback')}" @click="toggleTab('feedback')">
            <div class="chunky-icon--icon">
              <FeedbackIcon/>
            </div>
            <div class="chunky-icon--label">Feedback</div>
          </button>
        </div>
        <div class="tabs-contents">
          <main v-if="openTabs.includes('filter')">
            <div class="filter-wrapper">
              <input class="filter" v-model="filterState.filter" placeholder="Custom filter...">
              <small class="computed-filter" v-if="inDebugMode">{{computedFilters}}</small>
            </div>
            <div class="click-controls">
              <div class="horizontal-selector">
                <div class="label">First Published Year</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.year" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[2010 TO 9998]">New (2010+)
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[1985 TO 9998]">Modern (1985+)
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.year" value="[* TO 1924]">Public Domain (&lt;1924)
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div class="label">Has ebook/preview?</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value="true">Yes
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.has_ebook" value="false">No
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div class="label">Age Range</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="filterState.age" value>Any
                  </label>
                  <label>
                    <input type="radio" v-model="filterState.age" value="juvenile">Juvenile
                  </label>
                </div>
              </div>
              <div class="horizontal-selector">
                <div class="label">Language</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="quickLanguageSelect" value>Any
                  </label>
                  <label v-for="lang of top3Languages" :key="lang.key">
                    <input type="radio" v-model="quickLanguageSelect" :value="lang">{{lang.name.split(' / ')[0]}}
                  </label>
                  <label>
                    <input type="radio" v-model="quickLanguageSelect" value="custom">
                    <multiselect v-model="fullLanguageSelect"
                      placeholder="Other..."
                      :options="langOpts"
                      :multiple="true"
                      :internal-search="false"
                      :hide-selected="true"
                      track-by="key"
                      label="name"
                      :loading="langLoading"
                      selectLabel=""
                      @search-change="findLanguage"
                    >
                    </multiselect>
                  </label>
                </div>
              </div>
            </div>
            <!-- <pre>{{parsedFilter}}</pre> -->
          </main>
          <main class="click-controls" v-if="openTabs.includes('sort')">
              <div class="horizontal-selector">
                <div>Sort Order</div>
                <div class="options">
                  <label>
                    <input type="radio" v-model="sortState.order" value="editions">Most Editions
                  </label>
                  <label>
                    <input type="radio" v-model="sortState.order" value="new">Newest
                  </label>
                  <label>
                    <input type="radio" v-model="sortState.order" value="old">Oldest
                  </label>
                  <label title="I.e. Classification order. Note some books maybe missing when sorting by shelf order–we're working on it.">
                    <input type="radio" v-model="sortState.order" :value="`${settingsState.selectedClassification.field}_sort asc`" >Shelf Order
                  </label>
                  <label>
                    <input type="radio" v-model="sortState.order" :value="randomWithSeed">Random
                    <button
                      v-if="sortState.order.startsWith('random')"
                      @click="sortState.order = randomWithSeed = 'random_' + Date.now()"
                    >Shuffle</button>
                  </label>
                </div>
              </div>
          </main>
          <main class="click-controls" v-if="openTabs.includes('settings')">
            <div class="horizontal-selector">
              <div class="label">Classification</div>
              <div class="options">
                <label v-for="c of settingsState.classifications" :key="c.name" :title="c.longName">
                  <input type="radio" v-model="settingsState.selectedClassification" :value="c">
                  {{c.name}}
                </label>
              </div>
            </div>
            <div class="horizontal-selector" v-for="(opts, name) of styles" :key="name">
              <div class="label">{{name}} style</div>
              <div class="options">
                <label v-for="cls of opts.options" :key="cls">
                  <input type="radio" v-model="opts.selected" :value="cls">
                  {{cls}}
                </label>
              </div>
            </div>
            <div class="horizontal-selector">
              <div class="label">Label Fields</div>
              <div class="options">
                <label>
                  <input type="checkbox" v-model="settingsState.labels" value="classification">
                  Classifications
                </label>
                <label>
                  <input type="checkbox" v-model="settingsState.labels" value="first_publish_year">
                  First Publish Year
                </label>
                <label>
                  <input type="checkbox" v-model="settingsState.labels" value="edition_count">
                  Number of Editions
                </label>
              </div>
            </div>
          </main>
          <main class="feedback-panel" v-if="openTabs.includes('feedback')">
            <p>Welcome to Library Explorer! Library Explorer is currently in <b>beta</b>, so you might hit some bugs while you're browsing.</p>

            <p>
              If you have any feedback you'd like to give, please fill out our <a :href="googleForms.url" target="_blank">Feedback Form</a>.
              If you like what you see, and want to share it with others, why not <a :href="twitterUrl" target="_blank">Share on Twitter</a>?
            </p>
          </main>
        </div>
      </div>
    </div>
</template>

<script>
import lucenerQueryParser from 'lucene-query-parser';
import SettingsIcon from './icons/SettingsIcon';
import FilterIcon from './icons/FilterIcon';
import SortIcon from './icons/SortIcon';
import FeedbackIcon from './icons/FeedbackIcon';
import CONFIGS from '../configs';
import Multiselect from 'vue-multiselect';

export default {
    components: {
        FilterIcon,
        SortIcon,
        SettingsIcon,
        FeedbackIcon,
        Multiselect,
    },

    props: {
        filterState: Object,
        settingsState: Object,
        sortState: Object,
    },

    data() {
        return {
            googleForms: {
                url: 'https://docs.google.com/forms/d/e/1FAIpQLSe3ZypSJXr9omueQrEDI4mGc2M_v6iDNpDtPp9jrHaGn6wgpA/viewform?usp=sf_link',
            },
            tweet: {
                url: `${CONFIGS.OL_BASE_PUBLIC}/explore`,
                text: 'Browse millions of books in the @openlibrary Explorer',
                hashtags: 'EmpoweringLibraries,BookLovers',
            },

            langOpts: [],
            topLanguages: [],
            quickLanguageSelect: '',
            fullLanguageSelect: [],
            langLoading: false,
            // By default, random is set to the "hourly" random, so that the books stick
            // around for a while
            randomWithSeed: `random_${new Date().toISOString().split(':')[0]}`,

            openTabs: [],
            maxTabs: screen.width > 600 ? 5 : 1,
        }
    },

    async created() {
        const params = CONFIGS.LANG ? `?lang=${CONFIGS.LANG}` : '';
        this.topLanguages = await fetch(`${CONFIGS.OL_BASE_LANGS}/languages.json${params}`).then(r => r.json());
        this.langOpts = this.topLanguages;
    },

    watch: {
        quickLanguageSelect(newVal) {
            if (newVal === '') this.filterState.languages = [];
            else if (newVal === 'custom') this.filterState.languages = this.fullLanguageSelect;
            else this.filterState.languages = [newVal];
        },

        fullLanguageSelect(newVal) {
            this.filterState.languages = newVal;
        },

        ['sortState.order'](newVal) {
            const desiredLabel = {
                editions: 'edition_count',
                new: 'first_publish_year',
                old: 'first_publish_year',
                ddc_sort: 'classification',
                lcc_sort: 'classification',
            }[newVal];
            if (desiredLabel && !this.settingsState.labels.includes(desiredLabel)) {
                this.settingsState.labels.push(desiredLabel);
            }
        }
    },

    computed: {
        twitterUrl() {
            return `https://twitter.com/intent/tweet?${new URLSearchParams(this.tweet)}`;
        },
        activeFiltersCount() {
            return Object.values(this.filterState).filter(v => v?.length).length;
        },

        computedFilters() {
            const parts = this.filterState.solrQueryParts();
            const computedParts = parts[0] === this.filterState.filter ? parts.slice(1) : parts;
            return computedParts.length ? ` AND ${computedParts.join(' AND ')}` : '';
        },

        top3Languages() {
            return this.topLanguages.slice(0, 3);
        },

        parsedFilter() {
            return lucenerQueryParser.parse(this.filterState.filter);
        },

        inDebugMode() {
            return new URLSearchParams(location.search).get('debug') === 'true';
        },

        styles() {
            return this.inDebugMode ? this.settingsState.styles : Object.fromEntries(Object.entries(this.settingsState.styles).filter(([, val]) => !val.debugModeOnly));
        }
    },

    methods: {
        async findLanguage(query) {
            this.langLoading = true;

            if (!query) {
                // fetch top languages
                this.langOpts = this.topLanguages;
            } else {
                const params = new URLSearchParams({q: query, limit: 15});
                if (CONFIGS.LANG) {
                    params.set('lang', CONFIGS.LANG);
                }
                // Actually search
                this.langOpts = await fetch(`${CONFIGS.OL_BASE_LANGS}/languages/_autocomplete.json?${params}`)
                    .then(r => r.json());
            }

            this.langLoading = false;
        },

        toggleTab(tabName) {
            const index = this.openTabs.indexOf(tabName);
            if (index === -1) {
                this.openTabs.push(tabName);
                if (this.openTabs.length > this.maxTabs) {
                    this.openTabs.shift();
                }
            } else {
                this.openTabs.splice(index, 1);
            }
        }
    }
}
</script>


<style src="vue-multiselect/dist/vue-multiselect.min.css"></style>
<style lang="less">


.floating-controls-wrapper {
  position: -webkit-sticky;
  position: sticky;
  bottom: 0;
  left: 0;
  display: flex;
  justify-content: center;
  pointer-events: none;
  z-index: 20;

  .multiselect {
    width: auto;
    min-height: 0;
    display: inline-block;
    color: currentColor;
    transition: background-color 0.2s;
    border-radius: 4px;
    &:hover, &:focus, &:focus-within { background: white; }

    .multiselect__tags {
      background: transparent;
      padding-top: 0;
      min-height: 0;
      padding-bottom: 0;
      font-family: inherit;
      font-size: inherit;
      padding-left: 0;
    }

    .multiselect__select {
      padding: 0;
      height: 100%;
    }

    .multiselect__tag {
      margin-bottom: -5px;
      margin-top: 0;
      display: inline-flex;
      padding: 0;
      align-items: center;

      & > span {
        padding-left: 6px;
      }
    }

    .multiselect__tag-icon {
      position: static;
      margin-left: 0;
      &:after {
        font-size: 24px;
        font-weight: 100;
      }
    }

    .multiselect__tag {
      margin-right: 0;
      margin-left: 10px;
    }

    .multiselect__tags-wrap:first-child .multiselect__tag {
      margin-left: 0;
    }

    // Jumbo up for touch devices...
    .multiselect__tag {
      min-height: 34px;
    }
    .multiselect__tag-icon {
      width: 34px;
      height: 34px;
      line-height: 34px;
    }

    @media (pointer: fine) {
      // Make drop down arrow smaller on non-touch devices
      .multiselect__tags {
        padding-right: 22px;
      }
      .multiselect__select {
        width: 22px;
      }

      // Make the "X" button smaller for non-touch devices
      .multiselect__tag {
        min-height: 0;
      }
      .multiselect__tag-icon {
        width: 22px;
        height: 22px;
        line-height: 22px;
      }

      // Make the dropdown options less spaced out for non-touch devices
      .multiselect__option {
        min-height: 0;
        padding: 6px;
      }
    }

    .multiselect__placeholder {
      margin: 0;
      color: currentColor;
    }

    .multiselect__input:focus {
      width: 100% !important;
      height: 100%;
      margin: 0;
      padding: 2px !important;
    }

    .multiselect__content {
      display: flex !important;
      flex-direction: column;
    }
  }

  .chunky-icon {
    padding: 4px;
    margin: 4px;
    width: 52px;
    transition: background-color .2s;
    text-align: center;

    &--icon svg {
      width: 48px;
      height: 24px;
    }

    &--label {
      font-size: .8em;
      text-align: center;
    }
  }

  .floating-controls {
    pointer-events: all;
    display: flex;
    flex-direction: column-reverse;
    border-radius: 4px 4px 0 0;
    box-shadow: 0 0 5px rgba(0, 0, 0, .2);
    background: linear-gradient(to bottom, #fff, #ebdfc5 150%);
    max-width: 100%;
    max-height: 80vh;

    &.open .tab-bar {
      border-top: 1px solid rgba(0, 0, 0, .2);
    }
    .tab-bar {
      display: flex;
      justify-content: center;

      background: linear-gradient(to bottom, #fff, #ebdfc5 150%);
    }
    .tab-bar--tab {
      box-sizing: content-box;
      border: none;
      font-size: 100%;
      color: inherit;
      background-color: inherit;
      border-right: 1px solid rgba(0, 0, 0, .2);
      margin: 0;
      padding: 8px;
      &:last-child {
        border: 0;
      }

      cursor: pointer;
      transition: background-color .2s;
      &:hover {
        background-color: rgba(0, 0, 0, .1);
      }
      &.active {
        background-color: rgba(0, 0, 0, .1);
      }
    }
    .tabs-contents main {
      padding: 8px;
    }

    &.open {
      .tab-bar--tab {
        &:first-child {
          border-left: 1px solid rgba(0, 0, 0, .2);
        }
        &:last-child {
          border-right: 1px solid rgba(0, 0, 0, .2);
        }
      }
    }
  }
}

.click-controls {
  display: flex;
  flex-wrap: wrap;
}

.horizontal-selector {
  margin-right: 10px;
  margin-top: 5px;

  .label {
    font-size: 0.9em;
    margin-left: 5px;
    margin-bottom: -2px;
  }

  .options {
    border: 1px solid currentColor;
    border-radius: 4px;
  }

  .options label {
    display: inline-block;
    padding: 2px 4px;
    padding-top: 3px;

    &[title] {
      text-decoration: underline;
      text-decoration-style: dotted;
    }
  }
}

.filter-wrapper {
  border: 1px solid currentColor;
  background: white;

  border-radius: 4px;
  max-width: 100%;
  box-sizing: border-box;
  display: inline-block;

  input.filter {
    max-width: 100%;
    margin: 1px;
    padding: 5px;
    width: 150px;
    font-family: inherit;
    font-size: inherit;
    border: 0;
    border-radius: inherit;
    transition: width 0.2s;
    &:not(:placeholder-shown), &:focus {
      width: 300px;
    }
  }

  small.computed-filter {
    background: rgba(125,125,125,0.2);
    font-size: inherit;
    display: inline-block;
    opacity: 0.8;
    font-style: oblique;
    padding: 6px;
    padding-right: 8px;
    border-left: 1px dotted grey;
    text-decoration: underline;
    text-decoration-style: dotted;
  }
}

.feedback-panel {
  max-width: 300px;
  p { line-height: 1.1em; }
  a {
    color: inherit;
    padding: 4px 6px;
    margin-left: -6px;
    margin-right: -6px;
    transition: background-color 0.2s;
    border-radius: 4px;
    display: inline-block;

    &:hover { background-color: rgba(0, 0, 0, .1); }
  }
}
</style>
