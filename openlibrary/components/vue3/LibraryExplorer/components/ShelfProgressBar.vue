<template>
  <div class="sections">
    <div
      v-for="(section, i) in sections"
      :key="section.short"
      :title="section.name"
      :style="{ flex: section.count }"
      :class="{ active: index === i }"
    >
      <div
        v-if="index === i"
        class="marker"
        :style="{ left: `${(100 * section.offset) / section.count}%` }"
      ></div>
    </div>
  </div>
</template>

<script>
export default {
    props: {
        sections: Array,
        index: Number,
    },
}
</script>

<style>
.sections div:not(:last-child) {
  border-right: 1px solid var(--highlight-color, rgba(0, 0, 255, .15));
  box-sizing: border-box;
}

.sections div {
  transition: background .2s;
  background: transparent;
  position: relative;
}

.sections .marker {
  position: absolute;
  height: 100%;
  border-left: 2px solid var(--highlight-color, rgba(0, 0, 255, .15));
  border-right: 2px solid var(--highlight-color, rgba(0, 0, 255, .15));
}

.sections div.active {
  background: var(--highlight-color, rgba(0, 0, 255, .15));
}
</style>
