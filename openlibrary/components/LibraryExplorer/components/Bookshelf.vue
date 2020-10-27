<template>
  <div class="bookshelf">
    <Shelf
      v-for="lvl of node.children"
      :key="lvl.short"
      :parent="node"
      :node="lvl"
      :classification="classification"
      :expandBookshelf="expandBookshelf"
      :features="features"
      :filter="filter"
    />
  </div>
</template>

<script>
import Shelf from './Shelf';


export default {
    components: {
        Shelf
    },

    props: {
        classification: Object,
        node: Object,
        expandBookshelf: Function,
        features: Object,
        filter: String,
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
