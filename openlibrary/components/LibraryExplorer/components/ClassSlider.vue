<template>
  <div class="class-slider">
    <div class="lr-buttons">
      <button @click="index -= 1" v-if="prevSection">
        <RightArrowIcon
          style="transform: rotate(-180deg)"
          class="arrow-icon"
          :title="prevSection.short"
        />
      </button>
      <div class="classification-short">{{ activeSection.short }}</div>
      <button
        @click="index += 1"
        v-if="nextSection"
        :title="nextSection.short"
      >
        <RightArrowIcon class="arrow-icon" />
      </button>
    </div>
    <main>
      <ShelfProgressBar :sections="progressBarSections" :index="progressBarIndex" />
      <div class="labels" :style="{transform: `translateX(-${100 * index}%)`}">
        <div v-for="section in sections" :key="section.short">
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
    data() {
        return {};
    },

    computed: {
        index: {
            get() {
                return this.node.position == 'root' ? 0 : this.node.position + 1;
            },
            set(newVal) {
                this.node.position = newVal == 0 ? 'root' : newVal - 1;
            }
        },
        sections() {
            return [this.node, ...(this.node.children || [])];
        },

        progressBarSections() {
            return this.node.children || [this.node];
        },

        progressBarIndex() {
            return this.sections.length > 1 ? this.index - 1 : this.index;
        },

        activeSection() {
            return this.sections[this.index];
        },

        prevSection() {
            return this.sections[this.index - 1];
        },

        nextSection() {
            return this.sections[this.index + 1];
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
  overflow: clip;
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
  padding-top: 6px;
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
