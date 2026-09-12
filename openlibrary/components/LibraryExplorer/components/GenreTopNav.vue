<template>
  <div class="genre-top-nav-wrapper">
    <button
      class="genre-top-nav__item genre-top-nav__item--all"
      :class="{active: activeIndex === -1}"
      :aria-current="activeIndex === -1 ? 'true' : null"
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
          :aria-current="i === activeSortedIndex ? 'true' : null"
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
        nodes: {
            type: Array,
            required: true
        },
        // -1 means "All Genres" is the current selection, not one of `nodes`.
        activeIndex: {
            type: Number,
            required: true
        },
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
/* A horizontally scrolling rail of genre pills. Bespoke rather than ol-chip: a chip's
   selected state renders a close icon, which reads as "remove this filter", not "you are
   here". The rest/hover/selected/press mechanics below are copied from ol-chip so the rail
   still behaves like every other pill in the system. */
.genre-top-nav-wrapper {
  /* Positioning (sticky/top/z-index) belongs to .genre-sticky-header in BookRoom.vue,
     which pins this nav and the filter controls together as one unit. */
  display: flex;
  align-items: center;
  background: var(--color-surface-header);
  border-bottom: var(--border-width-divider) solid var(--color-border-subtle);
}

.genre-top-nav-scroll-region {
  position: relative;
  flex: 1;
  min-width: 0;
}

.genre-top-nav {
  display: flex;
  overflow-x: auto;
  gap: var(--spacing-inline-sm);
  padding: var(--spacing-inset-sm) var(--spacing-inset-md);
  scrollbar-width: thin;
}

.genre-top-nav__item {
  flex-shrink: 0;
  padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
  border: var(--border-width-control) solid var(--color-border-subtle);
  border-radius: var(--border-radius-chip);
  background: var(--color-surface);
  color: var(--color-text);
  /* Held at one weight and one size in every state: the selected pill changes color, not
     metrics, so selecting one never reflows the rail (see docs/ai/design.md). */
  font: inherit;
  font-size: var(--font-size-label-large);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-single);
  white-space: nowrap;
  cursor: pointer;
  /* Press feedback only -- hover lands instantly. */
  transition: transform var(--duration-press);
}

@media (hover: hover) and (pointer: fine) {
  .genre-top-nav__item:hover {
    background: var(--color-control-hover);
    border-color: var(--color-border);
  }
}

.genre-top-nav__item:active {
  transform: scale(var(--press-scale));
}

.genre-top-nav__item:focus-visible {
  outline: none;
  box-shadow: var(--box-shadow-focus);
}

.genre-top-nav__item.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary);
}

/* A saturated fill lightens rather than darkens on hover -- darkening an already-dark
   fill barely registers. brightness() carries the fill and the border together. */
@media (hover: hover) and (pointer: fine) {
  .genre-top-nav__item.active:hover {
    filter: brightness(1.1);
    background: var(--color-primary);
    border-color: var(--color-primary);
  }
}

/* Outside the scrolling rail, so it keeps its own gutter and stays put while the rail
   scrolls under the arrows. */
.genre-top-nav__item--all {
  margin-left: var(--spacing-inset-md);
  margin-right: var(--spacing-inline-md);
}

.genre-top-nav__arrow {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40px;
  border: 0;
  z-index: var(--z-index-local-1);
  display: flex;
  align-items: center;
  color: var(--color-text-secondary);
}

.genre-top-nav__arrow--left {
  left: 0;
  padding-left: var(--spacing-inset-xs);
  justify-content: flex-start;
  background: linear-gradient(to right, var(--color-surface-header) 45%, transparent);
}

.genre-top-nav__arrow--right {
  right: 0;
  padding-right: var(--spacing-inset-xs);
  justify-content: flex-end;
  background: linear-gradient(to left, var(--color-surface-header) 45%, transparent);
}

.genre-top-nav__arrow svg {
  width: 18px;
  height: 18px;
}
</style>
