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

import { deleteObservation } from '../ObservationService'


export default {
    name: 'Selections',
    components: {
        Chip
    },
    props: {
        allSelectedValues: {
            type: Object,
            required: true
        },
        work: {
            type: String,
            required: true
        },
        username: {
            type: String,
            required: true
        }
    },
    data: function() {
        return {
            classLists: {}
        }
    },
    methods: {
        removeItem: function(chipText) {
            const [type, value] = chipText.split(': ')

            const valueIndex = this.allSelectedValues[type].indexOf(value);
            const valueArr = this.allSelectedValues[type];
            valueArr.splice(valueIndex, 1);

            if (valueArr.length === 0) {
                delete this.allSelectedValues[type]
                Vue.delete(this.allSelectedValues, type)
            }

            deleteObservation(type, value, this.work, this.username)

            // Remove hover class:
            this.removeHoverClass(chipText);
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
