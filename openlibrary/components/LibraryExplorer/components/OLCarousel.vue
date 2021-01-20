<template>
  <div class="ol-carousel">
    <BooksCarousel :style="[status!='Loaded'?{'visibility':'hidden'}:'']" :observer="intersectionObserver" :books="results">
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

            /** @type {IntersectionObserver} */
            intersectionObserver: null,

            isVisible: false,

            /** @type {AbortController} */
            lastFetchAbortController: null,
        };
    },
    computed: {
        olUrl() {
            return `${CONFIGS.OL_BASE_SEARCH}/search?${new URLSearchParams({
                q: this.query,
                offset: this.offset,
                limit: this.limit
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
            this.status = 'Start';
            this.results.splice(0, this.results.length);
            this.numFound = null;
            this.error = null;
            if (this.isVisible) this.debouncedReloadResults();
        },

        isVisible(newVal) {
            if (newVal) this.reloadResults();
        }
    },

    created() {
        this.debouncedReloadResults = debounce(this.reloadResults, 1000);
        this.intersectionObserver = ('IntersectionObserver' in window) ? new IntersectionObserver(this.handleIntersectionChange, {
            root: this.$el,
            threshold: 1.0
        }) : null;
    },

    beforeDestroy() {
        this.intersectionObserver.disconnect();
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
                fields: 'key,title,author_name,cover_i,ddc,lcc,lending_edition_s'
            });

            const url = `${CONFIGS.OL_BASE_SEARCH}/search.json?${params.toString()}`;

            this.status = 'Loading';
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
