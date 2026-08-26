<template>
  <div
    class="shelf"
    :data-short="node.short"
  >
    <component
      :is="features.shelfLabel === 'slider' ? 'ClassSlider' : 'ShelfLabel'"
      :key="node.short"
      class="shelf-label"
      :node="node"
      :expanded="showShelfIndex"
      @toggle-index="showShelfIndex = !showShelfIndex"
    >
      <template #extra-actions>
        <button
          v-if="!hideExpand && node.children && node.children.length"
          :title="`See more books in ${node.short}: ${node.name}`"
          @click="expandBookshelf(parent, node)"
        >
          <ExpandIcon />
        </button>
      </template>
    </component>

    <OLCarousel
      class="shelf-carousel"
      :data-short="activeNode.short"
      :query="effectiveQuery"
      :node="activeNode"
      :sort="sort"
      :fetch-coordinator="fetchCoordinator"
    >
      <template #book-end-start>
        <div class="book-end-start">
          <h3>
            {{ activeNode.name }}
          </h3>
        </div>
      </template>

      <template #cover="{ book }">
        <BookCover3D
          v-if="features.book3d"
          :width="150"
          :height="200"
          :thickness="50"
          :book="book"
          :cover="features.cover"
        />
        <FlatBookCover
          v-else
          :book="book"
          :cover="features.cover"
        />
      </template>

      <template #cover-label="{ book }">
        <div
          v-if="book[classification.field] && labels.includes('classification')"
          :title="
            book[classification.field]
              .map(classification.fieldTransform)
              .join('\n')
          "
        >
          {{
            classification.fieldTransform(classification.chooseBest(book[classification.field]))
          }}
        </div>
        <div v-if="labels.includes('first_publish_year')">
          {{ book.first_publish_year }}
        </div>
        <div v-if="labels.includes('edition_count')">
          {{ book.edition_count }} editions
        </div>
      </template>
    </OLCarousel>
  </div>

  <!-- A sibling of .shelf, not a child: .shelf is `position: relative` (the anchor for the
       genre-mode baseboard label's `position: absolute; bottom: 3px`), so an in-flow list
       nested inside it would grow .shelf's height and drag that label down into the list
       instead of leaving it pinned to the shelf board above. -->
  <ShelfIndex
    v-if="showShelfIndex"
    class="shelf-index"
    :node="node"
  />
</template>

<script>
import OLCarousel from './OLCarousel.vue';
import ClassSlider from './ClassSlider.vue';
import ShelfLabel from './ShelfLabel.vue';
import BookCover3D from './BookCover3D.vue';
import FlatBookCover from './FlatBookCover.vue';
import ShelfIndex from './ShelfIndex.vue';
import ExpandIcon from './icons/ExpandIcon.vue';
import maxBy from 'lodash/maxBy';

class FetchCoordinator {
    constructor() {
        this.requestedFetches = [];
        /** @type { 'idle' | 'active' } */
        this.state = 'idle';

        this.runningRequests = 0;

        this.timeout = null;
        this.maxConcurrent = 6;
        this.groupingTime = 250;
    }

    async fetch({ priority, name }, ...args) {
        return new Promise((resolve, reject) => {
            this.enqueue({
                priority,
                name,
                args,
                resolve,
                reject,
            });
        });
    }

    enqueue(fetchRequest) {
        // console.log(`Enqueuing request #${this.requestedFetches.length + 1}: ${fetchRequest.name}`);
        this.requestedFetches.push(fetchRequest);
        this.activate();
    }

    activate() {
        if (this.requestedFetches.length && !this.timeout) {
            this.state = 'active';
            this.timeout = setTimeout(() => this.consume(), this.groupingTime);
        } else {
            this.state = 'idle';
        }
    }

    consume() {
        this.timeout = null;
        while ((this.maxConcurrent - this.runningRequests > 0) && this.requestedFetches.length) {
            const topRequest = maxBy(this.requestedFetches, f => f.priority());
            // console.log(`Completing request w p=${topRequest.priority()}: ${topRequest.name}`)
            this.runningRequests++;
            fetch(...topRequest.args)
                .then(r => {
                    this.runningRequests--;
                    topRequest.resolve(r);
                })
                .catch(e => {
                    this.runningRequests--;
                    topRequest.reject(e);
                });
            const indexToRemove = this.requestedFetches.indexOf(topRequest);
            this.requestedFetches.splice(indexToRemove, 1);
        }
        this.activate();
    }
}

const fetchCoordinator = new FetchCoordinator();

export default {
    components: {
        OLCarousel,
        ClassSlider,
        BookCover3D,
        FlatBookCover,
        ShelfIndex,
        ShelfLabel,
        ExpandIcon,
    },
    props: {
        /** @type {import('../utils').ClassificationNode} */
        node: Object,
        parent: Object,

        labels: Array,
        /** @type {import('../utils').ClassificationTree} */
        classification: Object,
        expandBookshelf: Function,
        features: Object,
        filter: String,
        sort: String,
        // Genre mode's "All Genres"/single-genre shelves aren't nested inside a real
        // bookcase the way DDC/LCC shelves are, so expandBookshelf(parent, node) has
        // no sensible parent bookcase to expand -- hide the button rather than wire up
        // a no-op/incorrect click.
        hideExpand: {
            type: Boolean,
            default: false,
        },
    },

    data() {
        return {
            showShelfIndex: false,
            fetchCoordinator: fetchCoordinator,
        };
    },

    computed: {
        activeNode() {
            return this.node.children && this.node.position !== 'root'
                ? this.node.children[this.node.position]
                : this.node;
        },

        // Genre mode only, and only for the AMBIGUOUS_SUBGENRES handful flagged in
        // generate_genre_classification.py (requiresIntersection): subject_key is a flat,
        // non-hierarchical tag, so a subgenre's own tag alone is normally trusted (a book
        // tagged with a specific-enough subgenre is usually already on-genre without also
        // requiring the parent tag -- live counts back this up broadly). requiresIntersection
        // is the opt-in exception, for a subgenre tag ambiguous enough on its own to pull in
        // clearly off-genre results (e.g. "Reimagining Democracy" carries "utopian" but
        // has nothing to do with Fantasy). hierarchyQuery is ancestor-prefixed only for
        // subgenres ("fantasy/utopian*") -- a top-level genre's own hierarchyQuery has no
        // slash -- so its prefix is exactly the parent genre's slug, regardless of whether
        // this subgenre is showing via the All Genres view's ClassSlider paging (where
        // `node` is the genre) or a drilled-into genre's own per-subgenre shelf (where
        // `node` IS the subgenre and `parent` is the genre).
        parentGenreShort() {
            if (!this.activeNode.requiresIntersection) return null;
            const slashIndex = this.activeNode.hierarchyQuery?.indexOf('/') ?? -1;
            return slashIndex === -1 ? null : this.activeNode.hierarchyQuery.slice(0, slashIndex);
        },

        effectiveQuery() {
            const field = this.sort.includes('_sort') ? `${this.classification.field}_sort` : this.classification.field;
            const q = this.classification.alphabeticalTopNav && this.parentGenreShort
                ? `(${this.activeNode.query} AND ${this.parentGenreShort}*)`
                : this.activeNode.query;
            return `${field}:${q} ${this.filter}`;
        },
    },
};
</script>

<style scoped>
.shelf-carousel {
  border: 3px solid black;
  margin-top: 10px;
  border-radius: 4px;
  height: 285px;
  background: #EEE;
  contain: strict;
}

.shelf :deep(.book) {
  justify-content: flex-end;
  margin-bottom: 10px;
}

.shelf :deep(.book:first-child .book-3d),
.shelf :deep(.book-end-start + .book .book-3d) {
  margin-left: 20px;
}

.shelf-label {
  border-radius: 0;
  background: black;
  color: white;
}

button {
  border: 0;
  background: 0;
  padding: 6px 8px;
  font: inherit;
  color: inherit;
}
</style>
