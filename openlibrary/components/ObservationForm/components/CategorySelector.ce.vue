<template>
  <div>
    <h3>Add your reviews:</h3>
    <p class="subtitle">Reviews listed above have been saved.</p>
    <div class="chip-group">
      <OLChip
        v-for="o in observationsArray"
        :key="o.id"
        :ref="'chip' + o.id"
        :text="o.label"
        selectable
        :selected="isSelected(o.id)"
        class="category-chip"
        @update-selected="updateSelected"
        >
        <template v-slot:before>
          <span class="symbol" v-html="displaySymbol(o.label)"></span>
        </template>
      </OLChip>
    </div>
  </div>
</template>

<script>
import OLChip from './OLChip.ce'

export default {
    name: 'CategorySelector',
    components: {
        OLChip
    },
    props: {
        /**
         * An array containing all of the observations.
         *
         * Observations have the following form:
         * @example
         * {
         *   'id': 20,
         *   'label': 'language',
         *   'description': 'What type of verbiage, nomenclature, or symbols are employed in this book?',
         *   'multi_choice': True,
         *   'values': ['technical', 'jargony', 'neologisms', 'slang', 'olde']
         * }
         */
        observationsArray: {
            type: Array,
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
         * The ID of the initially selected observation.
         */
        initialSelectedId: {
            type: Number,
            required: false,
            default: 0
        }
    },
    data: function() {
        return {
            /**
             * The ID of the selected book tag type.
             *
             * @type {number | null}
             */
            selectedId: this.initialSelectedId,
        }
    },
    methods: {
        /**
         * Updates the currently selected book tag type.
         *
         * @param {boolean} isSelected Whether or not a chip is currently selected.
         * @param {String} text The text displayed by a chip.
         */
        updateSelected: function(isSelected, text) {
            if (isSelected) {
                // TODO: This for loop shouldn't be necessary
                for (let i = 0; i < this.observationsArray.length; ++i) {
                    if (this.observationsArray[i].label === text) {
                        this.selectedId = this.observationsArray[i].id;
                        this.$emit('update-selected', this.observationsArray[i])
                    }
                }
            } else {
                this.selectedId = null;

                // Set ObservationForm's selected observation to null
                this.$emit('update-selected', null)
            }
        },
        /**
         * Returns `true` if the given ID matches that of the currently selected chip.
         *
         * @param {number} id A chip's id.
         */
        isSelected: function(id) {
            return this.selectedId === id
        },
        /**
         * Returns an HTML code denoting what symbol to display in a book tag type chip.
         *
         * Will return a bullet symbol if no book tags of a chip's type have been selected,
         * and a heavy checkmark otherwise.
         *
         * @returns {String} An HTML code representing selections of a type.
         */
        displaySymbol: function(type) {
            if (this.allSelectedValues[type] && this.allSelectedValues[type].length) {
                // &#10004; - Heavy checkmark
                return '&#10004;';
            }
            return '&bull;';
        }
    }
}
</script>

<style scoped>
h3 {
  margin-bottom: 0;
}

.subtitle {
  margin-top: 5px;
  color: #505050;
}

.chip-group {
  display: flex;
  flex-wrap: wrap;
}
.category-chip {
  margin-right: 1em;
  margin-bottom: .5em;
}

</style>
