<template>
  <div class="card-body">
    <OLChip
      v-for="item in values"
      :key="item + type"
      :text="item"
      :ref="'chip-' + item"
      selectable
      :selected="selectedValues.includes(item)"
      class="value-chip"
      @update-selected="updateSelected"
      />
  </div>
</template>

<script>
import OLChip from './OLChip.vue'

import { updateObservation } from '../ObservationService'

export default {
    name: 'CardBody',
    components: {
        OLChip
    },
    props: {
        /**
         * @type {string[]} All possible values for the current book tag type.
         */
        values: {
            type: Array,
            required: true
        },
        /**
         * Whether or not multiple values can be selected for the current book tag type.
         */
        multiSelect: {
            type: Boolean,
            required: false,
            default: false,
        },
        /**
         * The currently selected book tag type.
         */
        type: {
            type: String,
            required: true
        },
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
    methods: {
        /**
         * Updates the currently selected book tags when a value chip is clicked.
         *
         * POSTs message to the server, adding or deleting a book tag.
         *
         * @param {boolean} isSelected `true` if a chip is selected, `false` otherwise.
         * @param {String} text The text that the updated chip is displaying.
         */
        updateSelected: function(isSelected, text) {
            let updatedValues = this.allSelectedValues[this.type] ? this.allSelectedValues[this.type] : []

            if (isSelected) {
                if (this.multiSelect) {
                    updatedValues.push(text)
                    updateObservation('add', this.type, text, this.workKey, this.username)
                        .catch(() => {
                            updatedValues.pop();
                        })
                        .finally(() => {
                            this.allSelectedValues[this.type] = updatedValues;
                        })
                } else {
                    if (updatedValues.length) {
                        let deleteSuccessful = false;
                        updateObservation('delete', this.type, updatedValues[0], this.workKey, this.username)
                            .then(() => {
                                deleteSuccessful = true;
                            })
                            .finally(() => {
                                if (deleteSuccessful) {
                                    updateObservation('add', this.type, text, this.workKey, this.username)
                                        .then(() => {
                                            updatedValues = [text]
                                        })
                                        .finally(() => {
                                            this.allSelectedValues[this.type] = updatedValues;
                                        })
                                }
                            })
                    }
                }
            } else {
                const index = updatedValues.indexOf(text);
                updatedValues.splice(index, 1);
                updateObservation('delete', this.type, text, this.workKey, this.username)
                    .catch(() => {
                        updatedValues.push(text);
                    })
            }
        }
    },
    computed: {
        /**
         * Returns an array of all of this book tag type's currently selected values.
         */
        selectedValues: function() {
            return this.allSelectedValues[this.type]?.length ? this.allSelectedValues[this.type] : []
        }
    }
}
</script>

<style scoped>
.card-body {
  display: flex;
  flex-wrap: wrap;
  padding: 1em;
}

.value-chip {
  margin-right: 1em;
  margin-bottom: .5em;
}
</style>
