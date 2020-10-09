<template>
  <div class="bookshelf" :id="node.short">
    <div
      class="shelf"
      v-for="(lvl, i) of node.children"
      :key="lvl.short"
      :id="lvl.short"
    >
      <OLCarousel
        class="shelf-carousel"
        :data-short="
          lvl.children && lvl.position != 'root'
            ? lvl.children[lvl.position].short
            : lvl.short
        "
        :query="`${
          lvl.children && lvl.position != 'root'
            ? lvl.children[lvl.position].query
            : lvl.query
        } ${filter}`"
        :node="
          lvl.children && lvl.position != 'root'
            ? lvl.children[lvl.position]
            : lvl
        "
      >
        <template #book-end-start>
          <div class="book-end-start">
            <h3>
              {{
                lvl.children && lvl.position != "root"
                  ? lvl.children[lvl.position].name
                  : lvl.name
              }}
            </h3>
          </div>
        </template>

        <template v-slot:cover="{ book }" v-if="features.book3d">
          <BookCover3D
            :width="150"
            :height="200"
            :thickness="50"
            :book="book"
          />
        </template>

        <template v-slot:cover-label="{ book }">
          <span
            v-if="book[classification.field]"
            :title="
              book[classification.field]
                .map(classification.fieldTransform)
                .join('\n')
            "
            >{{
              classification.fieldTransform(book[classification.field][0])
            }}</span
          >
        </template>
      </OLCarousel>

      <component class="shelf-label" :node="lvl" :key="i" :is="features.shelfLabel == 'slider' ? 'ClassSlider' : 'ShelfLabel'">
        <template #extra-actions>
          <button title="Expand shelf" @click="expandBookshelf(node)" v-if="lvl.children && lvl.children.length">
            <ExpandIcon />
          </button>
        </template>
      </component>
    </div>
  </div>
</template>

<script>
import OLCarousel from './OLCarousel';
import ClassSlider from './ClassSlider';
import ShelfLabel from './ShelfLabel';
import BookCover3D from './BookCover3D';
import ExpandIcon from './icons/ExpandIcon.vue';

export default {
    components: {
        OLCarousel,
        ClassSlider,
        BookCover3D,
        ShelfLabel,
        ExpandIcon,
    },

    props: {
        classification: Object,
        node: Object,
        expandBookshelf: Function,
        features: Object,
        filter: String,
    }
};
</script>

<style>
@keyframes shelf-appear {
  from {
    opacity: 0;
    transform: scale(1.5);
  }
  from {
    opacity: 1;
    transform: scale(1);
  }
}

.bookshelf {
  border: 3px solid black;
  border-radius: 4px;
  background: black;
  flex-shrink: 0;
  z-index: 1;
  animation: shelf-appear .2s;

  transition-property: transform, opacity, filter;
  transition-duration: .2s;
  transform-origin: top center;
}

.shelf-carousel {
  border: 3px solid black;
  margin-top: 10px;
  border-radius: 4px;
  height: 285px;
  background: #EEE;
}

.book {
  justify-content: flex-end;
  margin-bottom: 10px;
}

.book:first-child .book-3d,
.book-end-start + .book .book-3d {
  margin-left: 20px;
}

.shelf-label {
  border-radius: 0;
  background: black;
  color: white;
}
</style>
