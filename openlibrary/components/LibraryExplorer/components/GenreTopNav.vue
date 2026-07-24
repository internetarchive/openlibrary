<template>
  <div class="genre-top-nav-wrapper">
    <button
      class="genre-top-nav__item genre-top-nav__item--all"
      :class="{active: activeIndex === -1}"
      @click="$emit('select-all')"
    >
      All Genres
    </button>

    <div class="genre-top-nav-scroll-region">
      <button
        v-if="canScrollLeft"
        class="genre-top-nav__arrow genre-top-nav__arrow--left"
        aria-label="Scroll genres left"
        @click="scrollByStep(-1)"
      >
        <RightArrowIcon style="transform: rotate(180deg)" />
      </button>

      <nav
        ref="nav"
        class="genre-top-nav"
        @scroll.passive="updateScrollState"
      >
        <button
          v-for="(node, i) of sortedNodes"
          :key="node.short"
          class="genre-top-nav__item"
          :class="{active: i === activeSortedIndex}"
          @click="$emit('select', node.originalIndex)"
        >
          {{ node.name }}
        </button>
      </nav>

      <button
        v-if="canScrollRight"
        class="genre-top-nav__arrow genre-top-nav__arrow--right"
        aria-label="Scroll genres right"
        @click="scrollByStep(1)"
      >
        <RightArrowIcon />
      </button>
    </div>
  </div>
</template>

<script>
import { nextTick } from 'vue';
import RightArrowIcon from './icons/RightArrowIcon.vue';

export default {
    components: {
        RightArrowIcon,
    },
    props: {
        /** @type {import('../utils').ClassificationNode[]} */
        nodes: Array,
        // -1 means "All Genres" is the current selection, not one of `nodes`.
        activeIndex: Number,
    },
    emits: ['select', 'select-all'],
    data() {
        return {
            canScrollLeft: false,
            canScrollRight: false,
        };
    },
    computed: {
        sortedNodes() {
            return this.nodes
                .map((node, originalIndex) => ({ ...node, originalIndex }))
                .sort((a, b) => a.name.localeCompare(b.name));
        },
        activeSortedIndex() {
            return this.sortedNodes.findIndex(n => n.originalIndex === this.activeIndex);
        },
    },
    watch: {
        async activeSortedIndex() {
            await nextTick();
            this.centerActiveItem();
        },
    },
    async mounted() {
        await nextTick();
        this.updateScrollState();
        this.centerActiveItem(false);
        window.addEventListener('resize', this.updateScrollState, { passive: true });
    },
    unmounted() {
        window.removeEventListener('resize', this.updateScrollState);
    },
    methods: {
        updateScrollState() {
            const el = this.$refs.nav;
            if (!el) return;
            // Small tolerance so sub-pixel scroll positions don't leave a stray arrow behind.
            this.canScrollLeft = el.scrollLeft > 4;
            this.canScrollRight = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
        },
        centerActiveItem(smooth = true) {
            const el = this.$refs.nav;
            if (!el) return;
            if (this.activeSortedIndex === -1) {
                // "All Genres" (outside the scrollable nav) is selected -- reset to the start
                // rather than leaving the list scrolled wherever it last was.
                el.scrollTo(smooth ? { left: 0, behavior: 'smooth' } : { left: 0 });
                return;
            }
            const activeEl = el.querySelector('.genre-top-nav__item.active');
            activeEl?.scrollIntoView(smooth ? { inline: 'center', block: 'nearest', behavior: 'smooth' } : { inline: 'center', block: 'nearest' });
        },
        scrollByStep(direction) {
            this.$refs.nav?.scrollBy({ left: direction * 240, behavior: 'smooth' });
        },
    },
};
</script>

<style scoped>
.genre-top-nav-wrapper {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  /* Light, elegant header cohesive with the cream bookcase wall (--wall cascades from
     .book-room.genre-mode). Opaque so shelves scroll cleanly underneath; a hairline border
     and soft shadow separate it from the case. */
  background: var(--wall, #e7dcc6);
  border-bottom: 1px solid rgba(74, 54, 35, .16);
  box-shadow: 0 6px 12px -9px rgba(74, 48, 20, .5);
}

.genre-top-nav-scroll-region {
  position: relative;
  flex: 1;
  min-width: 0;
}

.genre-top-nav {
  display: flex;
  overflow-x: auto;
  gap: 4px;
  padding: 10px 14px;
  scrollbar-width: thin;
}

.genre-top-nav__item {
  flex-shrink: 0;
  border: 0;
  background: none;
  color: #7a624a;
  font: inherit;
  font-size: .95em;
  padding: 6px 10px;
  border-radius: 999px;
  white-space: nowrap;
  transition: background-color .15s, color .15s;
}

.genre-top-nav__item:hover {
  background: rgba(74, 48, 20, .08);
  color: #4a3623;
}

.genre-top-nav__item.active {
  color: #33240f;
  font-weight: bold;
  font-size: 1.2em;
  background: rgba(74, 48, 20, .1);
}

.genre-top-nav__item--all {
  margin: 10px 0 10px 14px;
  border-right: 1px solid rgba(74, 54, 35, .22);
  padding-right: 14px;
  border-radius: 0;
}

.genre-top-nav__arrow {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40px;
  border: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  color: #5b4026;
}

.genre-top-nav__arrow--left {
  left: 0;
  padding-left: 4px;
  justify-content: flex-start;
  background: linear-gradient(to right, var(--wall, #e7dcc6) 45%, transparent);
}

.genre-top-nav__arrow--right {
  right: 0;
  padding-right: 4px;
  justify-content: flex-end;
  background: linear-gradient(to left, var(--wall, #e7dcc6) 45%, transparent);
}

.genre-top-nav__arrow svg {
  width: 18px;
  height: 18px;
}
</style>
