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
      <div class="classification-short" :class="this.direction">{{ activeSection.short }}</div>
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
      <div class="label" :class="this.direction">{{activeSection.name}}</div>
    </main>
    <div>
      <slot name="extra-actions" />
    </div>
  </div>
</template>

<script>
import RightArrowIcon from './icons/RightArrowIcon.vue';
import ShelfProgressBar from './ShelfProgressBar.vue';
export default {
    components: { RightArrowIcon, ShelfProgressBar },
    props: {
        node: Object
    },
    data() {
        return {
            direction: null,
        };
    },

    watch: {
        async index(newVal, oldVal) {
            if (typeof oldVal !== 'number') return;
            this.direction = newVal > oldVal ? 'slide-right' : 'slide-left';
            await new Promise(res => setTimeout(res, 200));
            this.direction = null;
        }
    },

    computed: {
        index: {
            get() {
                return this.node.position === 'root' ? 0 : this.node.position + 1;
            },
            set(newVal) {
                this.node.position = newVal === 0 ? 'root' : newVal - 1;
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

<style scoped lang="less">
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
  align-items: center;;
}

.class-slider main {
  @media (min-width: 450px) {
    position: relative;
  }
  overflow: hidden;
  overflow: clip;
  flex: 1;
  align-self: stretch;
  display: flex;
  justify-content: center;
}

button {
  border: 0;
  background: 0;
  padding: 6px 8px;
  font: inherit;
  color: inherit;
}

button:first-child {
  border-right: 2px solid rgb(161, 157, 157);
}
button:last-child {
  border-left: 2px solid #000;
}

.label {
  display: flex;
  justify-content: center;
  align-items: center;
  text-align: center;
  line-height: 1em;
  padding-bottom: 6px;
}

.sections {
  position: absolute;
  display: flex;
  left: 0;
  right: 0;
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

@keyframes slide-right {
  from { transform: translateX(20px) }
}

@keyframes slide-left {
  from { transform: translateX(-20px) }
}

.slide-right {
  animation: slide-right 0.2s ease;
}
.slide-left {
  animation: slide-left 0.2s ease;
}
</style>
