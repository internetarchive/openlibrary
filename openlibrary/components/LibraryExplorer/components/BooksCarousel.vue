<template>
  <transition-group name="bcbook" class="books-carousel" tag="div" @before-leave="beforeBookLeave">
    <div class="book-end-wrapper" key="book-end-start">
      <slot name="book-end-start"/>
    </div>

    <a class="book" v-for="book in books" :key="book.key" :href="`${OL_BASE_BOOKS}${book.key}`" target="_blank" :title="book.title">
      <slot name="cover" v-bind:book="book">
        <FlatBookCover :book="book"/>
      </slot>

      <div class="cover-label">
        <slot name="cover-label" v-bind:book="book"/>
      </div>
    </a>

    <div class="book-end-wrapper" key="book-end-end">
      <slot name="book-end"/>
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
