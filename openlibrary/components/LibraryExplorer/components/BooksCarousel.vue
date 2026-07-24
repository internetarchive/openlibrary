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
        books: Array
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

/* A small gold "shelf talker" standing in front of the book, bookstore-display style --
   absolutely positioned (doesn't affect cover sizing/flex layout the way an in-flow
   element would). Anchored to the book's *bottom* edge, not its top: covers vary in
   rendered height (different aspect ratios under object-fit: contain), but
   .books-carousel's align-items: flex-end bottom-aligns every .book to the same shelf
   line regardless -- anchoring to the bottom (and nudging past it with a negative
   offset, like a little card propped against the book's lower edge) keeps every placard
   on a shelf sitting at that same consistent height, rather than each one floating at
   whatever height its own book's top edge happens to land. Flat, not embossed: one soft
   shadow, no inset bevel. */
.rating-placard {
  position: absolute;
  top: 93%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1;
  padding: 2px 6px;
  background: #cea439;
  border: 1px solid #8a6d1f;
  border-radius: 9px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .4);
  font-size: 10px;
  font-family: Georgia, "Times New Roman", serif;
  font-weight: 700;
  letter-spacing: .02em;
  color: #3a2c0c;
  text-align: center;
  white-space: nowrap;
  pointer-events: none;
}
.rating-placard__star {
  color: #5c440e;
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
