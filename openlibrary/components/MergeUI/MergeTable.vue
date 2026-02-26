<template>
  <table class="main">
    <thead>
      <tr>
        <th />
        <th
          v-for="field in fields"
          :key="field"
        >
          {{ field.replace(/\_/g, ' ').replace(/\|/g, ', ') }}
        </th>
      </tr>
    </thead>
    <tbody>
      <MergeRow
        v-for="record in enhancedRecords"
        :key="record.key"
        :record="record"
        :fields="fields"
        :editions="editions"
        :lists="lists"
        :bookshelves="bookshelves"
        :ratings="ratings"
        :class="{ selected: selected[record.key]}"
        :cell-selected="isCellUsed"
        :merged="merge ? merge.record : null"
        :show_diffs="show_diffs"
      >
        <template #pre>
          <td
            v-if="['/type/edition','/type/work'].includes(record.type.key)"
            class="col-controls"
          >
            <input
              v-model="master_key"
              type="radio"
              name="master_key"
              title="Primary Record"
              :value="record.key"
            >
            <input
              v-model="selected[record.key]"
              type="checkbox"
              title="Include in Merge"
            >
          </td>
          <td v-else />
        </template>
      </MergeRow>
    </tbody>
    <tfoot>
      <MergeRow
        v-if="merge"
        :record="enhancedMergeRecord.record"
        :selected="selected"
        :fields="fields"
        :merged="enhancedMergeRecord"
      >
        <template #pre>
          <td />
        </template>
      </MergeRow>
      <tr v-else>
        <td :colspan="fields ? fields.length+1 : 1">
          <div>⏳</div>
        </td>
      </tr>
    </tfoot>
  </table>
</template>

<script>
/* eslint no-console: 0 */
import _ from 'lodash';
import MergeRow from './MergeRow.vue';
import { merge, get_editions, get_lists, get_bookshelves, get_ratings, get_author_names, fetchWithRetry } from './utils.js';
import CONFIGS from '../configs.js';


function olidToKey(olid) {
    const type = {
        W: 'works',
        M: 'books',
        A: 'authors'
    }[olid[olid.length - 1]];
    return `/${type}/${olid}`;
}

async function fetchRecords(olids) {
    if (olids.length > 1000) {
        throw new Error('Cannot fetch more than 1000 records at a time');
    }

    const query = {
        key: olids.map(olidToKey),
        limit: olids.length,
        '*': null,
    };
    const params = new URLSearchParams({query: JSON.stringify(query)});

    return (await fetchWithRetry(`${CONFIGS.OL_BASE_BOOKS}/query.json?${params}`)).json()
}

export default {
    name: 'MergeTable',
    components: {
        MergeRow
    },
    props: {
        olids: Array,
        show_diffs: Boolean,
        primary: String
    },
    data() {
        return {
            master_key: null,
            /** @type {{[key: string]: Boolean}} */
            selected: []
        };
    },
    asyncComputed: {
        async records() {
            const records = _.orderBy(
                await fetchRecords(this.olids),
                [
                    // Ensure orphaned editions are at the bottom of the list
                    record => record.type.key,
                    // Sort by key, so oldest records are at the top
                    record => parseFloat(record.key.match(/\d+/)[0]),
                ],
                ['desc', 'asc'],
            );

            let masterIndex = 0
            if (this.primary) {
                const primaryKey = `/works/${this.primary}`
                masterIndex = records.findIndex(elem => elem.key === primaryKey)
            }

            this.master_key = records[masterIndex].key
            this.selected = _.fromPairs(records.map(record => [record.key, record.type.key.includes('work')]));

            return records;
        },

        /** The records, with extra helpful metadata attached for display. Should NOT be saved to Open Library */
        async enhancedRecords(){
            if (!this.records) return null;

            let author_names;

            try {
                author_names = await get_author_names(this.records);
            } catch (error) {
                console.error('Error creating enhancedRecords:', error);
            }

            const enhanced_records = _.cloneDeep(this.records)

            for (const record of enhanced_records) {
                for (const entry of (record.authors || [])) {
                    // Support both author entry shapes: {author: {key: "..."}}, {key: "..."}
                    const authorKey = entry.author?.key ?? entry.key;
                    if (!authorKey) continue;
                    entry.name = author_names[authorKey.slice('/authors/'.length)];
                }
            }
            return enhanced_records
        },

        async editions() {
            if (!this.records) return null;

            const editionPromises = await Promise.all(
                this.records.map(r => r.type.key.includes('work') ? get_editions(r.key) : {size: 0})
            );
            const editions = editionPromises.map(p => p.value || p);
            const editionsMap = _.fromPairs(
                this.records.map((work, i) => [work.key, editions[i]])
            );

            // If any of the records are editions, insert the record as its own edition list
            Object.keys(editionsMap).forEach((key, index) => {
                if (key.includes('M')) editionsMap[key] = {size: 1, entries: [this.records[index]]};
            });

            return editionsMap;
        },

        async lists() {
            if (!this.records) return null;

            // We only need the count, so set limit=0 (waaaay faster!)
            const promises = await Promise.all(
                this.records.map(r => (r.type.key === '/type/work') ? get_lists(r.key, 0) : {})
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i]])
            );
        },
        async bookshelves() {
            if (!this.records) return null;

            const promises = await Promise.all(
                this.records.map(r => (r.type.key === '/type/work') ? get_bookshelves(r.key) : {})
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i]])
            );
        },

        async ratings() {
            if (!this.records) return null;

            const promises = await Promise.all(
                this.records.map(r => (r.type.key === '/type/work') ? get_ratings(r.key) : {})
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i]])
            );
        },
    },
    computed: {
        fields() {
            const at_start = ['covers'];
            const together = ['key', 'title', 'subtitle', 'authors', 'error'];
            const subjects = [
                'subjects',
                'subject_people',
                'subject_places',
                'subject_times'
            ];
            const record_data = [
                'created',
                'last_modified',
                'revision',
                'type',
                'location'
            ];
            const identifiers = [
                'first_publish_date',
                'dewey_number',
                'lc_classifications'
            ];
            const text_data = [
                'description',
                'excerpts',
                'first_sentence',
                'links'
            ];
            const exclude = [
                'latest_revision',
                'id',
            ];
            const recordFields = _.uniq(_.flatMap(this.records, Object.keys));
            const otherFields = _.difference(recordFields, [
                ...at_start,
                ...together,
                ...subjects,
                ...record_data,
                ...identifiers,
                ...text_data,
                ...exclude
            ]);
            const usedIdentifiers = _.intersection(identifiers, recordFields);
            const usedTextData = _.intersection(text_data, recordFields);
            return [
                ...at_start,
                together.join('|'),
                record_data.join('|'),
                'editions',
                'references',
                ...usedIdentifiers,
                subjects.join('|'),
                ...usedTextData,
                ...otherFields
            ];
        },
        merge() {
            if (!this.records || !this.editions || !this.master_key) return undefined;
            return this.build_merge(this.records);
        },
        enhancedMergeRecord() {
            if (!this.enhancedRecords || !this.editions || !this.master_key) return undefined;
            return this.build_merge(this.enhancedRecords);
        }
    },
    methods: {
        isCellUsed(record, field) {
            if (!this.merge) return false;
            return field in this.merge.sources
                ? this.merge.sources[field].includes(record.key)
                : record.key === this.master_key;
        },

        build_merge(records) {
            const master = records.find(r => r.key === this.master_key);
            const all_dupes = records
                .filter(r => this.selected[r.key])
                .filter(r => r.key !== this.master_key);
            const dupes = all_dupes.filter(r => r.type.key === '/type/work');
            const editions_to_move = _.flatMap(
                all_dupes,
                work => this.editions[work.key].entries
            );

            const [record, sources] = merge(master, dupes);

            const extras = {
                edition_count: _.sum(records.map(r => this.editions[r.key].size)),
                list_count: (this.lists) ? _.sum(records.map(r => this.lists[r.key].size)) : null
            };

            const unmergeable_works = records
                .filter(work => work.type.key === '/type/work' &&
        this.selected[work.key] &&
        work.key !== this.master_key &&
        this.editions[work.key].entries.length < this.editions[work.key].size)
                .map(r => r.key);

            return { record, sources, ...extras, dupes, editions_to_move, unmergeable_works };
        }
    }
};
</script>

<style>
:root {
  --row-height: 105px;
  --row-padding: 8px;
  --table-background: rgb(248, 248, 248);
  --selection-background: rgb(220, 224, 238);
}

body {
  font-size: .85em;
}
time {
  white-space: nowrap;
}

table.main {
  border-collapse: collapse;
  min-width: 100%;
}
table.main thead,
table.main tfoot {
  position: sticky;
  z-index: 300;
}
table.main > thead {
  top: 0;
}
table.main > thead > tr > th {
  font-variant: small-caps;
  margin-right: 4px;
  background: rgb(240, 237, 226);
}
table.main > tbody {
  background: var(--table-background);
}
table.main > tfoot {
  background: var(--selection-background);
  bottom: 0;
}
table.main > tfoot > tr {
  border-top: 4px double;
  box-shadow: 0 2px 4px inset black;
}
table.main > tfoot > tr > td > div {
  min-height: var(--row-height);
}

table.main > tbody > tr:hover,
table.main > tfoot > tr:hover {
  background: rgba(200, 200, 0, .1);
}
table.main > tbody > tr > td,
table.main > tfoot > tr > td {
  max-height: var(--row-height);
  max-width: 300px;
  position: relative;
  vertical-align: top;
  border-bottom: 4px solid rgba(255, 255, 255, 0.9);
  box-sizing: border-box;
  padding: 0;
}
table.main > tbody > tr > td > div,
table.main > tfoot > tr > td > div {
  height: calc(var(--row-height) - var(--row-padding) * 2);
  max-height: calc(var(--row-height) - var(--row-padding) * 2);
  overflow-y: auto;
  padding: var(--row-padding);
  margin-right: 4px;
}
table.main > tbody > tr > td > div.field-covers,
table.main > tfoot > tr > td > div.field-covers {
  width: 100px;
  overflow-y: auto;
  overflow-x: hidden;
  float: left;
  margin-right: var(--row-padding);
}
table.main > tbody > tr > td > div.field-covers .wrapper img,
table.main > tfoot > tr > td > div.field-covers .wrapper img {
  width: 100%;
}
table.main > tbody > tr > td > div.wrap-key--title--subtitle--authors--error,
table.main > tfoot > tr > td > div.wrap-key--title--subtitle--authors--error {
  min-width: 500px;
  padding: 0 0 calc(var(--row-padding) * 2) 0;
}
table.main > tbody > tr > td > div.wrap-key--title--subtitle--authors--error > div,
table.main > tfoot > tr > td > div.wrap-key--title--subtitle--authors--error > div {
  padding: var(--row-padding) var(--row-padding) 0 var(--row-padding);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
}
table.main > tbody > tr > td > div.wrap-key--title--subtitle--authors--error > div:last-child,
table.main > tfoot > tr > td > div.wrap-key--title--subtitle--authors--error > div:last-child {
  padding-bottom: var(--row-padding);
}
table.main > tbody > tr > td > div.wrap-key--title--subtitle--authors--error div.field-subtitle,
table.main > tfoot > tr > td > div.wrap-key--title--subtitle--authors--error div.field-subtitle {
  padding-left: 1em;
  padding-top: 0;
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location {
  white-space: nowrap;
  padding: var(--row-padding) 0 var(--row-padding) 0;
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div {
  padding: calc(var(--row-padding) / 2) var(--row-padding) 0 var(--row-padding);
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div:nth-child(1),
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div:nth-child(2),
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div:nth-child(1),
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div:nth-child(2) {
  padding-top: var(--row-padding);
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div:last-child,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div:last-child {
  padding-bottom: var(--row-padding);
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-created,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-created {
  padding-right: 0;
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified {
  padding-left: 0;
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-created,
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-created,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified {
  display: inline;
  font-size: 0.95em;
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified::before,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-last_modified::before {
  content: "…";
}
table.main > tbody > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-revision > div::before,
table.main > tfoot > tr > td > div.wrap-created--last_modified--revision--type--location > div.field-revision > div::before {
  content: "v";
}
table.main > tbody > tr > td > .td-container,
table.main > tfoot > tr > td > .td-container {
  overflow-y: auto;
  resize: vertical;
}
table.main > tbody > tr > td.col-key--title--subtitle--authors--error,
table.main > tbody > tr > .col-subjects--subject_people--subject_places--subject_times,
table.main > tbody > tr > td.col-editions,
table.main > tfoot > tr > td.col-key--title--subtitle--authors--error,
table.main > tfoot > tr > .col-subjects--subject_people--subject_places--subject_times,
table.main > tfoot > tr > td.col-editions {
  max-width: 100vw;
}
table.main > tbody .work:not(.selected) {
  opacity: .5;
}

.field-container {
  overflow-y: auto;
}

.field-container.selected {
  background: var(--selection-background);
}

td.col-controls {
  text-align: center;
  line-height: 2em;
}

div.field-error {
  font-weight: 700;
  color: red;
}

td.col-description {
  min-width: 200px;
}

td.col-description,
td.col-excerpts,
td.col-first_sentence,
td.col-links {
  font-size: .9em;
}
td.col-description div,
td.col-excerpts div,
td.col-first_sentence div,
td.col-links div {
  max-height: var(--row-height);
}
td.col-description ul,
td.col-excerpts ul,
td.col-first_sentence ul,
td.col-links ul {
  padding: 0;
  margin: 0;
}

div.field-lc_classifications li, div.field-dewey_number li {
  font-size: .9em;
  white-space: nowrap;
}

li.excerpt-item {
  padding-bottom: 0.4em;
}

.col-subjects--subject_people--subject_places--subject_times >
  div.wrap-subjects--subject_people--subject_places--subject_times {
  height: var(--row-height);
  max-height: var(--row-height);
  display: flex;
  flex-direction: column;
  padding: 0;
}
.col-subjects--subject_people--subject_places--subject_times >
  div.wrap-subjects--subject_people--subject_places--subject_times .field-container {
  min-height: 16px;
  padding: 4px;
  border-bottom: 2px solid var(--table-background);
  flex: 1 1 auto;
}
.col-subjects--subject_people--subject_places--subject_times >
  div.wrap-subjects--subject_people--subject_places--subject_times .field-container:last-child {
  border-bottom: 0;
}

.field-authors td.author-author {
  padding-right: 6px;
}
.field-authors thead,
.field-authors td.author-index,
.field-authors td.author-type {
  display: none;
}

ul.reset {
  padding: 0;
  margin: 0;
}
ul.reset > li {
  list-style: none;
}

.pill-list {
  min-width: 250px;
  text-align: center;
}
.pill {
  font-size: .9em;
  display: inline-block;
  white-space: nowrap;
  border: 1px solid;
  border-radius: 10px;
  padding: 0 6px;
  text-align: center;
  margin: 0 2px 1px 0;
  background: rgba(255, 255, 255, .4);
}

.field-subject_people::before {
  content: "👤";
  float: left;
  padding-left: 3px;
}
.field-subject_places::before {
  content: "🌎";
  float: left;
  padding-left: 3px;
}
.field-subject_times::before {
  content: "🕗";
  float: left;
  padding-left: 3px;
}

td.col-editions div.td-container {
  width: 400px;
  max-height: calc(var(--row-height) - 30px);
}

.col-references > div {
  white-space: nowrap;
}
.col-references > div > div {
  padding-bottom: var(--row-padding);
}

div.field-links li {
  margin-bottom: var(--row-padding);
}

.bookshelf-counts span:not(:first-child)::before {
  content: " / ";
}
</style>
