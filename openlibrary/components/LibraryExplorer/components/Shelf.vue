<template>
  <div class="shelf" :data-short="node.short">
    <OLCarousel
      class="shelf-carousel"
      :data-short="
        node.children && node.position != 'root'
          ? node.children[node.position].short
          : node.short
      "
      :query="`${
        node.children && node.position != 'root'
          ? node.children[node.position].query
          : node.query
      } ${filter}`"
      :node="
        node.children && node.position != 'root'
          ? node.children[node.position]
          : node
      "
    >
      <template #book-end-start>
        <div class="book-end-start">
          <h3>
            {{
              node.children && node.position != "root"
                ? node.children[node.position].name
                : node.name
            }}
          </h3>
        </div>
      </template>

      <template v-slot:cover="{ book }" v-if="features.book3d">
        <BookCover3D :width="150" :height="200" :thickness="50" :book="book" />
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

    <component
      class="shelf-label"
      :node="node"
      :key="node.short"
      :is="features.shelfLabel == 'slider' ? 'ClassSlider' : 'ShelfLabel'"
    >
      <template #extra-actions>
        <button
          :title="`See a list of the subsections of ${node.short}: ${node.name}`"
          v-if="features.shelfLabel == 'slider'"
          @click="showShelfIndex = !showShelfIndex"
        >
          <IndexIcon />
        </button>
        <button
          :title="`See more books in ${node.short}: ${node.name}`"
          @click="expandBookshelf(parent, node)"
          v-if="node.children && node.children.length"
        >
          <ExpandIcon />
        </button>
      </template>
    </component>

    <ShelfIndex class="shelf-index" :node="node" v-if="showShelfIndex" />
  </div>
</template>

<script>
import OLCarousel from './OLCarousel';
import ClassSlider from './ClassSlider';
import ShelfLabel from './ShelfLabel';
import BookCover3D from './BookCover3D';
import ShelfIndex from './ShelfIndex';
import ExpandIcon from './icons/ExpandIcon.vue';
import IndexIcon from './icons/IndexIcon.vue';

export default {
    components: {
        OLCarousel,
        ClassSlider,
        BookCover3D,
        ShelfIndex,
        ShelfLabel,
        ExpandIcon,
        IndexIcon,
    },
    props: {
        node: Object,
        parent: Object,

        classification: Object,
        expandBookshelf: Function,
        features: Object,
        filter: String,
    },

    data() {
        return {
            showShelfIndex: false,
        };
    }
};
</script>

<style scoped>
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
