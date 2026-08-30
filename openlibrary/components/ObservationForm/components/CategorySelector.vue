<template>
  <div>
    <h3>Add your reviews:</h3>
    <p class="subtitle">
      Reviews listed above have been saved.
    </p>
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
        <template #before>
          <span
            v-if="hasSelectedValues(o.label)"
            class="symbol"
          >&#10004;</span>
          <span
            v-else
            class="symbol"
          >&bull;</span>
        </template>
      </OLChip>
    </div>
  </div>
</template>

<script>
import OLChip from './OLChip.vue';

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
    emits: ['update-selected'],
    data: function() {
        return {
            /**
             * The ID of the selected book tag type.
             *
             * @type {number | null}
             */
            selectedId: this.initialSelectedId,
        };
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
                        this.$emit('update-selected', this.observationsArray[i]);
                    }
                }
            } else {
                this.selectedId = null;

                // Set ObservationForm's selected observation to null
                this.$emit('update-selected', null);
            }
        },
        /**
         * Returns `true` if the given ID matches that of the currently selected chip.
         *
         * @param {number} id A chip's id.
         */
        isSelected: function(id) {
            return this.selectedId === id;
        },
        /**
         * Returns `true` if any book tags of the given type have been selected.
         *
         * @param {String} type A book tag type.
         * @returns {boolean} Whether any selected values exist for the given type.
         */
        hasSelectedValues: function(type) {
            return !!(this.allSelectedValues[type] && this.allSelectedValues[type].length);
        }
    }
};
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
