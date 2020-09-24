<template>
  <div class="shelf-label">
    <details class="shelf-label--classes">
      <summary>
        <RightArrowIcon class="shelf-label--right-arrow"/>
        <div class="shelf-label--name">{{index == 'root' ? node.name : node.children[index].name}}</div>
      </summary>
      <ol class="shelf-label--subclasses">
        <li>
          <a
            :class="{ selected: index == 'root' }"
            href="#"
            @click.prevent="updateIndex('root')"
          >All {{node.short}} ({{node.count}})</a>
        </li>
        <li v-for="(child, i) of node.children || []" :key="i">
          <a
            :class="{ selected: index == i }"
            href="#"
            @click.prevent="updateIndex(i)"
          >{{child.name}} ({{child.count}})</a>
        </li>
      </ol>
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

export default {
    components: { RightArrowIcon },
    props: {
        node: Object
    },
    methods: {
        updateIndex(newIndex) {
            this.node.position = newIndex;
        }
    },
    data() {
        return {};
    },

    computed: {
        index() {
            return typeof this.node.position === 'undefined' || !this.node.children
                ? 'root'
                : this.node.position;
        },
        sections() {
            return this.node.children || [this.node];
        },
        total() {
            return this.sections.map(s => s.count).reduce((a, b) => a + b, 0);
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
}

.shelf-label--classes .shelf-label--right-arrow {
  transition: transform .2s;
  margin-right: 5px;
}

.shelf-label--classes[open] .shelf-label--right-arrow {
  transform: rotate(90deg);
}

.shelf-label--subclasses {
  column-count: 2;
  list-style: none;
  padding-left: 0;
}

.shelf-label--subclasses a {
  color: inherit;
  text-decoration: none;
  display: block;
  padding: 5px;

  transition: background-color .2s;
  /* border: 1px solid white; */
  margin: 0;
}

.shelf-label--subclasses a.selected {
  background-color: white;
  border-radius: 4px;
  color: black;
}
.shelf-label--subclasses a:not(.selected):hover {
  background-color: rgba(255, 255, 255, .1);
}
</style>
