<template>
  <div class="bookshelf" :id="node.short">
    <div class="bookshelf-name">
      <h2>
        <span class="classification-short">{{ node.short }}</span>
        {{ node.name }}
      </h2>
      <button @click="expandBookshelf(node)" v-if="node.children">
        <ExpandIcon />
      </button>
    </div>
    <div
      class="shelf"
      v-for="(lvl, i) of node.children"
      :key="i"
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

      <ClassSlider
        v-if="features.shelfLabel == 'slider'"
        class="shelf-label"
        :node="lvl"
        :key="i"
      />
      <ShelfLabel v-else :node="lvl" :key="i">
        <template #extra-actions>
          <button title="Expand shelf" @click="expandBookshelf(node)">
            <ExpandIcon />
          </button>
        </template>
      </ShelfLabel>
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

<style >
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

.bookshelf-name {
  max-width: 800px;
  margin: auto;
  text-align: center;
  color: white;

  margin: 20px 0;
}

.bookshelf-name h2 {
  color: white;
  font-weight: 300;
  font-size: 1.5em;
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
