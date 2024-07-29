<template>
  <ol class="shelf-label--subclasses">
    <li>
      <a
        :class="{ selected: index === 'root' }"
        href="#"
        @click.prevent="index = 'root'"
        >
          All {{ node.short }}
          <span class="shelf-label--subclasses--count">{{ node.count }}</span>
        </a
      >
    </li>
    <li v-for="(child, i) of node.children || []" :key="i">
      <a
        :class="{ selected: index === i }"
        href="#"
        @click.prevent="index = i"
        >
          {{ child.name }}
          <span class="shelf-label--subclasses--count">{{ child.count }}</span>
        </a
      >
    </li>
  </ol>
</template>

<script>
export default {
  props: {
    node: Object,
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
    },
  },
};
</script>

<style>
.shelf-label--subclasses {
  column-count: 2;
  list-style: none;
  padding-left: 0;
  margin-top: 0;
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
