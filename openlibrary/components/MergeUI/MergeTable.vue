<template>
  <table class="main">
    <thead>
      <tr>
        <th rowspan="2"></th>
        <th rowspan="2"></th>
        <th v-for="field in fields" :key="field" rowspan="2">{{field}}</th>
        <th colspan="3">Backreferences</th>
      </tr>
      <tr>
        <th>Editions</th>
        <th>Lists</th>
        <th>Reading Log</th>
      </tr>
    </thead>
    <tbody>
      <MergeRow
        v-for="record in records"
        :key="record.key"
        :record="record"
        :fields="fields"
        :class="{ selected: selected[record.key] }"
        :cellSelected="isCellUsed"
        :merged="merge ? merge.record : null"
      >
        <template #pre>
          <td>
            <input type="radio" name="master_key" v-model="master_key" :value="record.key" />
          </td>
          <td>
            <input type="checkbox" v-model="selected[record.key]" />
          </td>
        </template>
        <template #post>
          <td v-if="editions">
            {{editions[record.key].size}} edition{{editions[record.key].size == 1 ? '' : 's'}}
            <div class="td-container" style="width: 400px;">
              <EditionSnippet
                v-for="edition in editions[record.key].entries"
                :key="edition.key"
                :edition="edition"
              />
            </div>
          </td>
          <td v-if="lists" style="white-space: nowrap;">
            <a :href="`${record.key}/-/lists`">{{lists[record.key].size}} list{{lists[record.key].size == 1 ? '' : 's'}}</a>
          </td>
          <td v-else>⏳</td>
          <td class="bookshelf-counts" style="white-space: nowrap;">
            <div v-if="bookshelves">
              <span v-for="(value, name, index) in bookshelves[record.key]" :key="index" :title="name">
                {{value}}
              </span>
            </div>
            <div v-else>⏳ / ⏳ / ⏳</div>

            <div>
              Ratings:
                <span v-if="ratings">{{ratings[record.key].summary.count}}</span>
                <span v-else>⏳</span>
            </div>
          </td>
        </template>
      </MergeRow>
    </tbody>
    <tfoot>
      <MergeRow v-if="merge" :record="merge.record" :selected="selected" :fields="fields">
        <template #pre>
          <td />
          <td />
        </template>
        <template #post>
          <td>{{merge.edition_count}} edition{{merge.edition_count == 1 ? '' : 's'}}</td>
          <td>{{merge.list_count}} list{{merge.list_count == 1 ? '' : 's'}}</td>
          <td>??</td>
        </template>
      </MergeRow>
      <tr v-else><td>⏳</td></tr>
    </tfoot>
  </table>
</template>

<script>
/* eslint no-console: 0 */
import _ from 'lodash';
import Vue from 'vue';
import AsyncComputed from 'vue-async-computed';
import MergeRow from './MergeRow.vue';
import EditionSnippet from './EditionSnippet.vue';
import { merge, get_editions, get_lists, get_bookshelves, get_ratings } from './utils.js';

Vue.use(AsyncComputed);

/**
 * @param {string} olid
 */
function fetchRecord(olid) {
    const type = {
        W: 'works',
        M: 'books',
        A: 'authors'
    }[olid[olid.length - 1]];
    const endpoint = `/${type}/${olid}.json`;
    // FIXME Fetch from prod openlibrary.org, otherwise it's outdated
    const url = location.host.endsWith('.openlibrary.org') ? `https://openlibrary.org${endpoint}` : endpoint;
    return fetch(url).then(r => r.json());
}

export default {
    name: 'MergeTable',
    components: {
        EditionSnippet,
        MergeRow
    },
    data() {
        const sorted = _.sortBy(this.olids, olid =>
            parseFloat(olid.match(/\d+/)[0])
        );
        return {
            master_key: `/works/${sorted[0]}`,
            /** @type {{[key: string]: Boolean}} */
            selected: _.fromPairs(this.olids.map(olid => [`/works/${olid}`, true]))
        };
    },
    props: {
        olids: Array
    },
    asyncComputed: {
        async records() {
            const sorted = _.sortBy(this.olids, olid =>
                parseFloat(olid.match(/\d+/)[0])
            );
            return await Promise.all(sorted.map(fetchRecord));
        },

        async editions() {
            if (!this.records) return null;

            const editionPromises = await Promise.all(
                this.records.map(r => get_editions(r.key))
            );
            const editions = editionPromises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, editions[i]])
            );
        },

        async lists() {
            if (!this.records) return null;

            // We only need the count, so set limit=0 (waaaay faster!)
            const promises = await Promise.all(
                this.records.map(r => get_lists(r.key, 0))
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i]])
            );
        },
        async bookshelves() {
            if (!this.records) return null;

            const promises = await Promise.all(
                this.records.map(r => get_bookshelves(r.key))
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i].counts])
            );
        },

        async ratings() {
            if (!this.records) return null;

            const promises = await Promise.all(
                this.records.map(r => get_ratings(r.key))
            );
            const responses = promises.map(p => p.value || p);
            return _.fromPairs(
                this.records.map((work, i) => [work.key, responses[i]])
            );
        },

        async merge() {
            if (!this.master_key || !this.records || !this.editions || !this.lists || !this.bookshelves)
                return undefined;

            const master = this.records.find(r => r.key === this.master_key);
            const dupes = this.records
                .filter(r => this.selected[r.key])
                .filter(r => r.key !== this.master_key);
            const records = [master, ...dupes];
            const editions_to_move = _.flatMap(
                dupes,
                work => this.editions[work.key].entries
            );

            const [record, sources] = merge(master, dupes);

            const extras = {
                edition_count: _.sum(records.map(r => this.editions[r.key].size)),
                list_count: _.sum(records.map(r => this.lists[r.key].size))
            };

            return { record, sources, ...extras, dupes, editions_to_move };
        }
    },
    methods: {
        isCellUsed(record, field) {
            if (!this.merge) return false;
            return field in this.merge.sources
                ? this.merge.sources[field].includes(record.key)
                : record.key === this.master_key;
        }
    },
    computed: {
        fields() {
            const at_start = ['covers'];
            const together = ['key', 'title', 'subtitle', 'authors'];
            const subjects = [
                'subjects',
                'subject_people',
                'subject_places',
                'subject_times'
            ];
            const at_end = [
                'created',
                'last_modified',
                'revision',
                'type'
            ];
            const exclude = [
                'latest_revision'
            ];
            const recordFields = _.uniq(_.flatMap(this.records, Object.keys));
            const middleFields = _.difference(recordFields, [
                ...at_start,
                ...together,
                ...subjects,
                ...at_end,
                ...exclude
            ]);
            return [
                ...at_start,
                together.join('|'),
                subjects.join('|'),
                ...middleFields,
                at_end.join('|')
            ];
        }
    }
};
</script>

<style lang="less">
@row-height: 80px;

body {
  font-size: .9em;
}
time {
  white-space: nowrap;
}

table {
  thead,
  tfoot {
    position: sticky;
    background: white;
    z-index: 300;
  }
  thead {
    top: 0;
  }
  tfoot {
    bottom: 0;
  }
  & > tbody > tr,
  & > tfoot > tr {
    &:hover {
      background: rgba(200, 200, 0, .2);
    }
    & > td {
      position: relative;

      & > .td-container {
        max-height: @row-height;
        overflow-y: auto;
        resize: horizontal;
      }
    }
  }

  & > tbody .work:not(.selected) {
    opacity: .5;
  }
}

.field-container {
  max-height: @row-height;
  overflow-y: auto;
}

td.col-description {
  min-width: 200px;
  font-size: .9em;
}

.field-covers {
  width: 100px;
  overflow-y: auto;
  overflow-x: hidden;
  float: left;
  img {
    width: 100%;
  }
  margin-right: 8px;
}
.col-key--title--subtitle--authors {
  display: block;
  border: 1px solid rgba(0, 0, 0, .5);
  border-radius: 5px;

  & > div {
    width: 300px;
    overflow-y: auto;
    max-height: 100px;
  }
}

.col-subjects--subject_people--subject_places--subject_times .field-container {
  border: 1px solid rgba(0, 0, 0, .3);
}

.field-authors {
  thead {
    display: none;
  }
  td:nth-child(0),
  td:nth-child(1),
  td:nth-child(2) {
    display: none;
  }
}

ul.reset {
  padding: 0;
  margin: 0;
  & > li {
    list-style: none;
  }
}

.pill-list {
  min-width: 300px;
  text-align: center;
}
.pill {
  display: inline-block;
  white-space: nowrap;
  border: 1px solid;
  border-radius: 10px;
  padding: 0 6px;
  text-align: center;
  margin: 0 2px 1px 0;
  background: rgba(255, 255, 255, .4);
}

table {
  border-collapse: collapse;
}
tfoot > tr {
  border-top: 4px double;
  box-shadow: 0 2px 4px inset black;
}

td {
  border: 1px solid rgba(255, 255, 255, .9);
  padding: 4px;
  box-sizing: border-box;
}

.field-container.selected {
  background: rgba(0, 50, 200, .2);
}

.field-subject_people::before {
  content: "🕴";
  float: left;
}
.field-subject_places::before {
  content: "🗺";
  float: left;
}
.field-subject_times::before {
  content: "⌚";
  float: left;
}
.bookshelf-counts span:not(:first-child)::before {
  content: " / ";
}

.field-created, .field-last_modified { display: inline; }
.field-last_modified::before { content: " … "; }
.field-revision > div::before { content: "v"; }
</style>
