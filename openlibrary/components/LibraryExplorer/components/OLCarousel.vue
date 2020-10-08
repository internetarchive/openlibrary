<template>
  <div class="ol-carousel">
    <BooksCarousel v-if="status == 'Loaded' || results.length" :books="results">
      <template v-slot:cover-label="{book}">
        <slot name="cover-label" v-bind:book="book"/>
      </template>

      <template v-slot:cover="{book}">
        <slot name="cover" v-bind:book="book"/>
      </template>

      <template #book-end-start>
        <slot name="book-end-start"/>
      </template>
      <template #book-end>
        <div class="book-end">
          <small>{{node.offset-results.length}}-{{node.offset}} of {{numFound}}</small>
          <button class="load-more" @click="loadResults">Load more</button>
          <a class="view-all" :href="olUrl" target="_blank">View all</a>
        </div>
      </template>
    </BooksCarousel>
    <transition>
      <div class="status-text" v-if="status == 'Errored'">Something went wrong...</div>
    </transition>
    <transition>
      <div class="status-text" v-if="status == 'Loading'">Loading...</div>
    </transition>

    <!-- <button class="load-books" @click="loadResults">Load books!</button> -->
  </div>
</template>

<script>
import BooksCarousel from './BooksCarousel.vue';
import debounce from 'lodash/debounce';
// import * as Vibrant from "node-vibrant";

// window.Vibrant = Vibrant;

export default {
    components: { BooksCarousel },
    props: {
        query: String,
        node: Object,
        limit: {
            type: Number,
            default: 20
        }
    },
    data() {
        return {
            /** @type {'Start' | 'Loading' | 'Loaded' | 'Errored'} */
            status: 'Start',
            results: [],
            numFound: null,
            error: null,

            displayedUrl: null,

            /** @type {IntersectionObserver} */
            intersectionObserver: null,

            isVisible: false,
        };
    },
    computed: {
        olUrl() {
            return `https://dev.openlibrary.org/search?${new URLSearchParams({
                q: this.query,
                offset: this.node.lastOffset || 0,
                limit: this.limit
            })}`;
        }
    },
    watch: {
        query(newVal, oldVal) {
            this.node.offset = 0;
            if (this.isVisible) this.debouncedLoadResults();
        },

        isVisible(newVal) {
            if (newVal) this.reloadResults();
        }
    },

    created() {
        this.debouncedLoadResults = debounce(this.loadResults, 1000);
        this.intersectionObserver = ('IntersectionObserver' in window) ? new IntersectionObserver(this.handleIntersectionChange, {
            rootMargin: '100px'
        }) : null;
    },

    mounted() {
        this.intersectionObserver.observe(this.$el);
    },
    beforeDestroy() {
        this.intersectionObserver.unobserve(this.$el);
    },

    methods: {
        /**
         * @param {IntersectionObserverEntry[]} entries
         */
        handleIntersectionChange(entries) {
            // Use `intersectionRatio` because of Edge 15's
            // lack of support for `isIntersecting`.
            // See: https://github.com/w3c/IntersectionObserver/issues/211
            const isIntersecting = entries[0].intersectionRatio > 0;
            this.isVisible = isIntersecting;
        },

        uniq(list) {
            const seen = new Set();
            return list.filter(x => !seen.has(x) && seen.add(x));
        },
        async reloadResults() {
            if (typeof this.node.lastOffset !== 'undefined') return;
            else return await this.loadResults();
        },
        async loadResults() {
            const params = new URLSearchParams({
                q: this.query,
                offset: this.node.offset,
                limit: this.limit,
                fields: 'key,title,author_name,cover_i,ddc,lcc,lending_edition_s'
            });
            const url =
        `https://dev.openlibrary.org/search.json?${params.toString()}`;

            // Already showing
            if (
                url === this.displayedUrl &&
        this.node.offset === this.node.lastOffset &&
        this.query === this.node.lastQuery
            ) {
                return;
            }
            this.displayedUrl = url;
            this.node.lastOffset = this.node.offset;
            this.node.lastQuery = this.query;
            this.status = 'Loading';
            try {
                const r = await fetch(url, { cache: 'force-cache' }).then(r =>
                    r.json()
                );
                this.status = 'Loaded';
                this.results.splice(0, this.results.length, ...r.docs);
                this.numFound = r.numFound;
                if (!this.node.offset) this.node.offset = 0;
                this.node.offset += r.docs.length;
            } catch (e) {
                this.error = e;
                this.status = 'Errored';
                this.results.splice(0, this.results.length);
            }
        }
    }
};
</script>


<style scoped>
.load-books {
  width: 100%;
  height: 50px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
  margin-bottom: 4px;
}

@keyframes slide-down {
  from {
    transform: translate(-50%, -20px);
    opacity: 0;
  }
  to {
    transform: translate(-50%, 0);
    opacity: 1;
  }
}

.status-text {
  position: absolute;
  top: 0;
  text-align: center;
  background: black;
  color: white;
  padding: 4px 8px;
  border-radius: 0 0 4px 4px;
  left: 50%;
  transform: translateX(-50%);
}

.status-text.v-enter-active {
  animation: slide-down .2s;
}
.status-text.v-leave-active {
  animation: slide-down .2s reverse;
}
.book-end {
  padding: 20px;
  margin: 10px;
  display: flex;
  flex-direction: column;
}
.book-end small {
  white-space: nowrap;
}
.book-end .load-more {
  align-self: center;
  white-space: nowrap;
  line-height: 2em;
}
.book-end .view-all {
  padding: 5px;
  text-align: center;
}

.ol-carousel {
  min-height: 100px;
  text-align: center;
  overflow: hidden;
  position: relative;
}
</style>
