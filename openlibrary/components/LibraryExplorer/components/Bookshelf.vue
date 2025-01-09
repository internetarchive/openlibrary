<template>
  <div class="bookshelf">
    <Shelf
      v-for="lvl of node.children"
      :key="lvl.short"
      :parent="node"
      :node="lvl"
      :classification="classification"
      :expandBookshelf="expandBookshelf"
      :labels="labels"
      :features="features"
      :filter="filter"
      :sort="sort"
    />
  </div>
</template>

<script>
import Shelf from './Shelf.vue';


export default {
    components: {
        Shelf
    },

    props: {
        classification: Object,
        node: Object,
        expandBookshelf: Function,
        labels: Array,
        features: Object,
        filter: String,
        sort: String,
    },

};
</script>

<style>
@keyframes bookshelf-appear {
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
  animation: bookshelf-appear .2s;

  transition-property: transform, opacity, filter;
  transition-duration: .2s;
  transform-origin: top center;
}
</style>
