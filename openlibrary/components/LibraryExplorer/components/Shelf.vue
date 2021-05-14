<template>
  <div class="shelf" :data-short="node.short">
    <component
      class="shelf-label"
      :node="node"
      :key="node.short"
      :is="features.shelfLabel == 'slider' ? 'ClassSlider' : 'ShelfLabel'"
    >
      <template #extra-actions>
        <button
          :title="`See a list of the subsections of ${node.short}: ${node.name}`"
          v-if="features.shelfLabel == 'slider' && node.children"
          :class="{selected: showShelfIndex}"
          @click="showShelfIndex = !showShelfIndex"
        >
          <IndexIcon />
        </button>
        <button
          :title="`See more books in ${node.short}: ${node.name}`"
          @click="expandBookshelf(parent, node)"
          v-if="node.children && node.children.length"
        >
          <ExpandIcon />
        </button>
      </template>
    </component>

    <ShelfIndex class="shelf-index" :node="node" v-if="showShelfIndex" />

    <OLCarousel
      class="shelf-carousel"
      ref="olCarousel"
      :data-short="
        node.children && node.position != 'root'
          ? node.children[node.position].short
          : node.short
      "
      :query="`${
        node.children && node.position != 'root'
          ? node.children[node.position].query
          : node.query
      } ${filter}`"
      :node="
        node.children && node.position != 'root'
          ? node.children[node.position]
          : node
      "
      :sort="sort"
      :fetchCoordinator="fetchCoordinator"
    >
      <template #book-end-start>
        <div class="book-end-start">
          <h3>
            {{
              node.children && node.position != "root"
                ? node.children[node.position].name
                : node.name
            }}
          </h3>
        </div>
      </template>

      <template v-slot:cover="{ book }">
        <BookCover3D
            v-if="features.book3d"
            :width="150" :height="200" :thickness="50" :book="book"
            :fetchCoordinator="fetchCoordinator"
            :containerIntersectionRatio="$refs.olCarousel.intersectionRatio"
            :cover="features.cover"
        />
        <FlatBookCover v-else :book="book" :cover="features.cover" />
      </template>

      <template v-slot:cover-label="{ book }">
        <div
          v-if="book[classification.field] && labels.includes('classification')"
          :title="
            book[classification.field]
              .map(classification.fieldTransform)
              .join('\n')
          "
          >{{
            classification.fieldTransform(classification.chooseBest(book[classification.field]))
          }}</div>
        <div v-if="labels.includes('first_publish_year')">{{book.first_publish_year}}</div>
        <div v-if="labels.includes('edition_count')">{{book.edition_count}} editions</div>
      </template>
    </OLCarousel>

  </div>
</template>

<script>
import OLCarousel from './OLCarousel';
import ClassSlider from './ClassSlider';
import ShelfLabel from './ShelfLabel';
import BookCover3D from './BookCover3D';
import FlatBookCover from './FlatBookCover';
import ShelfIndex from './ShelfIndex';
import ExpandIcon from './icons/ExpandIcon.vue';
import IndexIcon from './icons/IndexIcon.vue';
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
        // console.log(`Enqueing request #${this.requestedFetches.length + 1}: ${fetchRequest.name}`);
        this.requestedFetches.push(fetchRequest);
        this.activate();
    }

    activate() {
        if (this.requestedFetches.length && !this.timeout) {
            this.state = 'active'
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
        IndexIcon,
    },
    props: {
        node: Object,
        parent: Object,

        labels: Array,
        classification: Object,
        expandBookshelf: Function,
        features: Object,
        filter: String,
        sort: String,
    },

    data() {
        return {
            showShelfIndex: false,
            fetchCoordinator: fetchCoordinator,
        };
    }
};
</script>

<style scoped>
.shelf-carousel {
  border: 3px solid black;
  margin-top: 10px;
  border-radius: 4px;
  height: 285px;
  background: #EEE;
}

.shelf >>> .book {
  justify-content: flex-end;
  margin-bottom: 10px;
}

.shelf >>> .book:first-child .book-3d,
.shelf >>> .book-end-start + .book .book-3d {
  margin-left: 20px;
}

.shelf-label {
  border-radius: 0;
  background: black;
  color: white;
}
</style>
