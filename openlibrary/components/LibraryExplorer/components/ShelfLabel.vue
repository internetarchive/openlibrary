<template>
  <div class="shelf-label">
    <details class="shelf-label--classes">
      <summary>
        <RightArrowIcon class="shelf-label--right-arrow"/>
        <div class="shelf-label--name">{{index === 'root' ? node.name : node.children[index].name}}</div>
      </summary>
      <ShelfIndex :node="node" />
    </details>
    <div class="shelf-label--controls">
      <slot name="extra-actions"/>
      <!-- <select class="sort-selector">
        <option>Popular</option>
        <option>Newest</option>
        <option>Shelf Order</option>
      </select>-->
    </div>
  </div>
</template>


<script>
import RightArrowIcon from './icons/RightArrowIcon.vue';
import ShelfIndex from './ShelfIndex.vue';

export default {
    components: { RightArrowIcon, ShelfIndex },
    props: {
        node: Object
    },

    computed: {
        index: {
            get() {
                return typeof this.node.position === 'undefined' || !this.node.children
                    ? 'root'
                    : this.node.position;
            },
            set(newVal) {
                return this.node.position = newVal;
            },
        }
    }
};
</script>

<style>
.shelf-label {
  position: relative;
}

.shelf-label--controls {
  position: absolute;
  top: 0;
  right: 0;
  height: 2em;
  display: flex;
}

.shelf-label--controls > button {
  background: none;
  border: none;
  color: inherit;
}

.sort-selector {
  border: 0;
}

.shelf-label--classes > summary {
  display: flex;
  padding: 10px;
}

.shelf-label--classes > summary::marker { display: none; }


.shelf-label--classes .shelf-label--right-arrow {
  transition: transform .2s;
  margin-right: 5px;
}

.shelf-label--classes[open] .shelf-label--right-arrow {
  transform: rotate(90deg);
}
</style>
