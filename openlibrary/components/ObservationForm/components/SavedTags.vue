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
        <OLChip
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
        </OLChip>
      </div>
  </div>
</template>

<script>
import OLChip from './OLChip.vue'

import { updateObservation } from '../ObservationService'


export default {
    name: 'SavedTags',
    components: {
        OLChip
    },
    props: {
        /**
         * An object containing all of the patron's currently selected book tags.
         *
         * @example
         * {
         *   "mood": ["joyful"],
         *   "genres": ["sci-fi", "anthology"]
         * }
         */
        allSelectedValues: {
            type: Object,
            required: true
        },
        /**
         * The work key.
         *
         * @example
         * /works/OL123W
         */
        workKey: {
            type: String,
            required: true
        },
        /**
         * The patron's username.
         */
        username: {
            type: String,
            required: true
        }
    },
    data: function() {
        return {
            /**
             * Contains class strings for each selected book tag
             *
             * @example
             * {
             *   "mood: joyful": "hover",
             *   "genre: sci-fi": ""
             * }
             *
             * @type {Object}
             */
            classLists: {}
        }
    },
    methods: {
        /**
         * Removes a book tag from a patron's selections.
         *
         * @param {String} chipText The text of the selected tag chip, in the form "<type>: <value>"
         */
        removeItem: function(chipText) {
            const [type, value] = chipText.split(': ')

            const valueIndex = this.allSelectedValues[type].indexOf(value);
            const valueArr = this.allSelectedValues[type];
            valueArr.splice(valueIndex, 1);

            updateObservation('delete', type, value, this.workKey, this.username)
                .catch(() => {
                    valueArr.push(value);
                })
                .finally(() => {
                    if (valueArr.length === 0) {
                        delete this.allSelectedValues[type]
                    }
                })

            // Remove hover class:
            this.removeHoverClass(chipText);
        },
        /**
         * Adds `hover` class to a chip.
         *
         * @param {String} value The chip's key.
         */
        addHoverClass: function(value) {
            this.classLists[value] = 'hover';
        },
        /**
         * Sets a chip's class list to an empty string.
         *
         * @param {String} value The chip's key.
         */
        removeHoverClass: function(value) {
            this.classLists[value] = ''
        },
        /**
         * Returns the class list string for the chip with the given key.
         *
         * @param {String} value The chip's key
         * @returns The chip's class list string.
         */
        getClassList: function(value) {
            return this.classLists[value] ? this.classLists[value] : ''
        }
    },
    computed: {
        /**
         * An array of a patron's book tags.
         */
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
