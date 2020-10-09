<template>
  <div class="class-slider">
    <div class="lr-buttons">
      <button @click="updateIndex(index - 1)" v-if="index > 0">
        <RightArrowIcon
          style="transform: rotate(-180deg)"
          class="arrow-icon"
          :title="sections[index - 1].short"
        />
      </button>
      <div class="classification-short">{{ sections[index].short }}</div>
      <button
        @click="updateIndex(index + 1)"
        v-if="index < sections.length - 1"
        :title="sections[index + 1].short"
      >
        <RightArrowIcon class="arrow-icon" />
      </button>
    </div>
    <main>
      <div class="sections">
        <div
          v-for="(section, i) in sections"
          :key="section.short"
          :title="section.name"
          :style="{flex: section.count}"
          :class="{active: index == i}"
        >
          <div
            v-if="index == i"
            class="marker"
            :style="{left: `${100 * section.offset / section.count}%`}"
          ></div>
        </div>
      </div>
      <div class="labels" :style="{transform: `translateX(-${100 * index}%)`}">
        <div v-for="(section, i) in sections" :key="section.short">
          {{section.name}}
          <br>
          <small>{{section.count}} books</small>
        </div>
      </div>
    </main>
    <div>
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
import RightArrowIcon from './icons/RightArrowIcon';
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
            return this.node.position || 0;
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

<style scoped>
.arrow-icon {
  margin-bottom: -2px;
}
.class-slider {
  position: relative;
  border: 2px solid black;
  border-radius: 4px;
  width: 100%;
  display: flex;
  min-height: 3em;
  box-sizing: border-box;
}

.class-slider main {
  position: relative;
  overflow: hidden;
  flex: 1;
  display: flex;
}

.class-slider main .labels {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
  transition: transform .2s;
}

.labels div {
  flex-shrink: 0;
  width: 100%;
  height: 100%;
  text-align: center;
}

button {
  border: 0;
  background: 0;
  padding: 6px 8px;
  font: inherit;
  color: inherit;
}

button:first-child {
  border-right: 2px solid #000;
}
button:last-child {
  border-left: 2px solid #000;
}

.sections {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
}

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

.lr-buttons {
  display: flex;
  align-items: center;
}

.classification-short {
  padding: 0 2px;
}

.classification-short:first-child {
  padding-left: 15px;
}
.classification-short:last-child {
  padding-right: 15px;
}

small {
  opacity: .8;
}
</style>
