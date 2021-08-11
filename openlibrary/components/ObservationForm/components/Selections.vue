<template>
  <div class="selections" v-show="selectedValues.length">
    <div
      v-if="!selectedValues.length"
      class="no-selections-message"
      >
      No tags selected.
    </div>
    <div
      v-else
      class="selection-panel"
      >
        <Chip
          v-for="value in selectedValues"
          :key="value"
          :text="value"
          :ref="value"
          :class-list="getClassList(value)"
          class="selection-chip"
          >
          <template v-slot:after>
            <span
              class="close-icon"
              title="Remove value"
              @mouseover="addHoverClass(value)"
              @mouseout="removeHoverClass(value)"
              @click="removeItem(value)"
              >
                &times;
            </span>
          </template>
        </Chip>
      </div>
  </div>
</template>

<script>
import Vue from 'vue'

import Chip from './Chip'

export default {
    name: 'Selections',
    components: {
        Chip
    },
    props: {
        allSelectedValues: {
            type: Object,
            required: true
        }
    },
    data: function() {
        return {
            classLists: {}
        }
    },
    methods: {
        removeItem: function(value) {
            const splitText = value.split(': ')

            const valueIndex = this.allSelectedValues[splitText[0]].indexOf(splitText[1]);
            const valueArr = this.allSelectedValues[splitText[0]];
            valueArr.splice(valueIndex, 1);
            Vue.set(this.allSelectedValues, splitText[0], valueArr);

            // Remove hover class:
            Vue.set(this.classLists, value, '');

            // TODO: event
            this.$emit('remove-value', splitText[0], splitText[1])
        },
        addHoverClass: function(value) {
            Vue.set(this.classLists, value, 'hover')
        },
        removeHoverClass: function(value) {
            Vue.set(this.classLists, value, '')
        },
        getClassList: function(value) {
            return this.classLists[value] ? this.classLists[value] : ''
        }
    },
    computed: {
        selectedValues: function() {
            const results = [];

            for (const type in this.allSelectedValues) {
                for (const value of this.allSelectedValues[type]) {
                    results.push(`${type}: ${value}`)
                }
            }

            return results;
        }
    }
}
</script>

<style scoped>
.no-selections-message {
  margin-bottom: 1em;
}

.selection-panel {
  display: flex;
  flex-wrap: wrap;
}

.selection-chip {
  margin-right: 1em;
  margin-bottom: .5em;
}

.close-icon {
  cursor: pointer;
}

.hover {
  border-color: red;
  color: red;
}
</style>
