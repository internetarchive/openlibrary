<template>
  <transition-group
    name="bcbook"
    class="books-carousel"
    tag="div"
    @before-leave="beforeBookLeave"
  >
    <div
      key="book-end-start"
      class="book-end-wrapper"
    >
      <slot name="book-end-start" />
    </div>

    <a
      v-for="book in books"
      :key="book.key"
      class="book"
      :href="`${OL_BASE_BOOKS}${book.key}`"
      target="_blank"
      :title="book.title"
    >
      <slot
        name="cover"
        :book="book"
      >
        <FlatBookCover :book="book" />
      </slot>

      <div
        v-if="book.ratings_count && book.ratings_average"
        class="rating-placard"
      >
        <span class="rating-placard__star">★</span> {{ book.ratings_average.toFixed(1) }} by {{ book.ratings_count }}
      </div>

      <div class="cover-label">
        <slot
          name="cover-label"
          :book="book"
        />
      </div>
    </a>

    <div
      key="book-end-end"
      class="book-end-wrapper"
    >
      <slot name="book-end" />
    </div>
  </transition-group>
</template>

<script>
import FlatBookCover from './FlatBookCover.vue';
import CONFIGS from '../../configs';

export default {
    components: { FlatBookCover },
    props: {
        books: {
            type: Array,
            default: () => []
        }
    },
    data() {
        return {
            OL_BASE_BOOKS: CONFIGS.OL_BASE_BOOKS
        };
    },
    methods: {
        beforeBookLeave(el) {
            const left = el.getBoundingClientRect().left + this.$el.scrollLeft;
            el.style.left = `${left}px`;
        }
    }
};
</script>


<style>
.books-carousel {
  display: flex;
  width: 100%;
  height: 100%;
  overflow-x: scroll;
  overflow-y: hidden;
  align-items: flex-end;
  position: relative;
}

.book {
  margin-left: 5px;
  display: flex;
  flex-direction: column;
  min-height: 90%;
  color: inherit;
  text-decoration: none;
}

/* The rating badge, absolutely positioned so it doesn't affect cover sizing or the flex
   layout the way an in-flow element would. Anchored to the book's *bottom* edge, not its
   top: covers vary in rendered height (different aspect ratios under object-fit: contain),
   but .books-carousel's align-items: flex-end bottom-aligns every .book to the same shelf
   line regardless -- so anchoring to the bottom keeps every badge on that same line,
   rather than each one floating at whatever height its own cover's top edge lands at. */
.rating-placard {
  position: absolute;
  bottom: var(--spacing-2xs);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-index-local-1);
  padding: 0 var(--spacing-inset-xs);
  background: var(--color-surface);
  border: var(--border-width-control) solid var(--color-border-subtle);
  border-radius: var(--border-radius-badge);
  box-shadow: var(--box-shadow-raised);
  font-size: var(--font-size-label-small);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-snug);
  /* The average and the count both vary per book, so fix the digit width or the badge
     jitters as you scan along a shelf. */
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
  text-align: center;
  white-space: nowrap;
  pointer-events: none;
}
.rating-placard__star {
  color: var(--color-icon-muted);
}

.bcbook-enter,
.bcbook-leave-to {
  transform: translateY(30px);
  opacity: 0;
}

.bcbook-move {
  transition: all .5s;
}

.bcbook-leave-active,
.bcbook-enter-active {
  transition-property: transform, opacity;
  transition-duration: .5s;
}
.bcbook-leave-active {
  position: absolute !important;
}

.book-end-wrapper {
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
}

img.cover {
  flex: 1;
  object-fit: contain;
  object-position: bottom;
  width: 150px;
}
div.cover {
  flex: 1;
  width: 150px;
  text-align: center;
  display: flex;
  align-items: center;
  background: grey;
}

.cover-label {
  flex-shrink: 0;
  padding: 2px;
  text-align: left;
}

.cover-label div {
  padding: 2px 4px;
}
</style>
