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
      <ShelfProgressBar :sections="sections" :index="index" />
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
import ShelfProgressBar from './ShelfProgressBar';
export default {
    components: { RightArrowIcon, ShelfProgressBar },
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
