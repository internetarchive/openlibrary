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
        <div class="book-end" v-if="offset > 0">
          <small>{{offset}}-{{offset + results.length}} of {{numFound}}</small>
          <button class="load-more" @click="loadPrevPage" :disabled="offset == 0">Load previous</button>
          <a class="view-all" :href="olUrl" target="_blank">View all</a>
        </div>
      </template>
      <template #book-end>
        <div class="book-end">
          <small>{{offset}}-{{offset + results.length}} of {{numFound}}</small>
          <button class="load-more" @click="loadNextPage" :disabled="offset + results.length == numFound">Load next</button>
          <a class="view-all" :href="olUrl" target="_blank">View all</a>
        </div>
      </template>
    </BooksCarousel>
    <transition>
      <div class="status-text" v-if="status == 'Errored'">Something went wrong... <button @click="reloadResults('reload')">Retry</button></div>
    </transition>
    <transition>
      <div class="status-text" v-if="status == 'Loading'">Loading...</div>
    </transition>
  </div>
</template>

<script>
import BooksCarousel from './BooksCarousel.vue';
import debounce from 'lodash/debounce';
import Vue from 'vue';
import CONFIGS from '../configs';
// import * as Vibrant from "node-vibrant";

// window.Vibrant = Vibrant;

class CarouselCoordinator {
    constructor() {
        this.maxRenderedOffscreen = Math.ceil(navigator.deviceMemory) || 8;
        this.currentlyRenderedOffscreen = [];
        this.log = false;
    }

    registerRenderedOffscreenCarousel(carousel) {
        this.currentlyRenderedOffscreen.push(carousel);
        this.log && console.log('CarouselCoordinator', `Now ffscreen -- ${carousel.query}`);
        if (this.currentlyRenderedOffscreen.length > this.maxRenderedOffscreen) {
            const toRemove = this.currentlyRenderedOffscreen.shift();
            this.log && console.log('CarouselCoordinator', `Culling offscreen carousel -- ${carousel.query}`);
            toRemove.unrender();
        }
    }

    registerOnscreenCarousel(carousel) {
        const index = this.currentlyRenderedOffscreen.indexOf(carousel);
        if (index != -1) {
            this.log && console.log('CarouselCoordinator', `Carousel no longer offscreen -- ${carousel.query}`);
            this.currentlyRenderedOffscreen.splice(index, 1);
        }
    }
}

const carouselCoordinator = new CarouselCoordinator();

export default {
    components: { BooksCarousel },
    props: {
        query: String,
        node: Object,
        fetchCoordinator: Object,
        sort: {
            default: 'editions',
        },
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

            /** @type {IntersectionObserver} */
            intersectionObserver: null,
            isVisible: false,
            intersectionRatio: 0,

            /** @type {AbortController} */
            lastFetchAbortController: null,
        };
    },
    computed: {
        olUrl() {
            return `${CONFIGS.OL_BASE_SEARCH}/search?${new URLSearchParams({
                q: this.query,
                offset: this.offset,
                sort: this.sort,
                limit: this.limit,
            })}`;
        },

        offset: {
            get() { return this.node.requests[this.query]?.offset ?? 0; },
            set(newVal) {
                if (!this.node.requests[this.query]) {
                    Vue.set(this.node.requests, this.query, { offset: 0 });
                }
                return this.node.requests[this.query].offset = newVal;
            },
        }
    },
    watch: {
        query() {
            this.unrender();
            if (this.isVisible) this.debouncedReloadResults();
        },

        sort() {
            this.unrender();
            if (this.isVisible) this.debouncedReloadResults();
        },

        isVisible(newVal) {
            if (newVal) {
                carouselCoordinator.registerOnscreenCarousel(this);
                this.reloadResults();
            } else {
                carouselCoordinator.registerRenderedOffscreenCarousel(this);
            }
        }
    },

    created() {
        this.debouncedReloadResults = debounce(this.reloadResults, 1000);
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
            this.intersectionRatio = entries[0].intersectionRatio;
            this.isVisible = isIntersecting;
        },

        unrender() {
            this.status = 'Start';
            this.results.splice(0, this.results.length);
            this.numFound = null;
            this.error = null;
        },

        async reloadResults(cache='force-cache') {
            return await this.loadResults(this.offset, cache);
        },

        async loadResults(offset, cache='force-cache') {
            // Don't re-fetch if already there
            if (offset == this.offset && this.results.length) return;

            this.lastFetchAbortController?.abort();
            if ('AbortController' in window) this.lastFetchAbortController = new AbortController();

            const params = new URLSearchParams({
                q: this.query,
                offset,
                limit: this.limit,
                sort: this.sort,
                fields: 'key,title,author_name,cover_i,ddc,lcc,lending_edition_s,first_publish_year,edition_count',
            });

            const url = `${CONFIGS.OL_BASE_SEARCH}/search.json?${params.toString()}`;

            this.status = 'Loading';
            const fetch = this.fetchCoordinator ?
                this.fetchCoordinator.fetch.bind(this.fetchCoordinator, { priority: () => 10 + this.intersectionRatio, name: this.query }) :
                fetch;
            try {
                const r = await fetch(url, {
                    cache,
                    signal: this.lastFetchAbortController?.signal,
                }).then(r => r.json());
                this.status = 'Loaded';
                this.results.splice(0, this.results.length, ...r.docs);
                this.numFound = r.numFound;
            } catch (e) {
                this.error = e;
                this.status = 'Errored';
            }
        },

        async loadNextPage() {
            const newOffset = this.offset + this.results.length;
            await this.loadResults(newOffset);
            if (this.status == 'Loaded') this.offset = newOffset;
        },

        async loadPrevPage() {
            const newOffset = this.offset - this.limit;
            await this.loadResults(newOffset);
            if (this.status == 'Loaded') this.offset = newOffset;
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
  color: inherit;
}

.ol-carousel {
  min-height: 100px;
  text-align: center;
  overflow: hidden;
  position: relative;
}
</style>
