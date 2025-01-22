<template>
  <div class="observation-form" ref="form">
    <SavedTags
      :all-selected-values="allSelectedValues"
      :work-key="work_key"
      :username="username"
      />
    <CategorySelector
      ref="categories"
      :observations-array="observationsArray"
      :all-selected-values="allSelectedValues"
      :initial-selected-id="getSelectedId"
      @update-selected="updateSelected"
      />
    <ValueCard
      v-if="selectedObservation"
      ref="value-card"
      :type="selectedObservation.label"
      :description="selectedObservation.description"
      :multi-select="selectedObservation.multi_choice"
      :values="selectedObservation.values"
      :all-selected-values="allSelectedValues"
      :work-key="work_key"
      :username="username"
      />
  </div>
</template>

<script>
import CategorySelector from './ObservationForm/components/CategorySelector.vue'
import SavedTags from './ObservationForm/components/SavedTags.vue'
import ValueCard from './ObservationForm/components/ValueCard.vue'

import { decodeAndParseJSON, resizeColorbox } from './ObservationForm/Utils'

export default {
    name: 'ObservationForm',
    components: {
        CategorySelector,
        SavedTags,
        ValueCard
    },
    props: {
        /**
         * URI encoded JSON string representation of the book tags schema.
         *
         * @see /openlibrary/core/observations.py
         */
        schema: {
            type: String,
            required: true
        },
        /**
         * URI encoded JSON string representation of all of a patron's selected book tags.
         *
         * @example
         * {
         *   "mood": ["joyful"],
         *   "genres": ["sci-fi", "anthology"]
         * }
         */
        observations: {
            type: String,
            required: true
        },
        /**
         * The work key.
         *
         * @example
         * /works/OL123W
         */
        work_key: {
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
             * An object representing the currently selected tag type.
             *
             * @example
             * {
             *   'id': 20,
             *   'label': 'language',
             *   'description': 'What type of verbiage, nomenclature, or symbols are employed in this book?',
             *   'multi_choice': true,
             *   'values': ['technical', 'jargony', 'neologisms', 'slang', 'olde']
             * }
             */
            selectedObservation: null,
            /**
             * An object containing all of the patron's currently selected book tags.
             *
             * @example
             * {
             *   "mood": ["joyful"],
             *   "genres": ["sci-fi", "anthology"]
             * }
             */
            allSelectedValues: {},
            /**
             * An array containing all book tag types and values.
             */
            observationsArray: null,
        }
    },
    methods: {
        /**
         * Sets the currently selected book tag type to a new value.
         *
         * @param {Object | null} observation The new selected observation, or `null` if no type is selected.
         */
        updateSelected: function(observation) {
            this.selectedObservation = observation
        },
        /**
         * Randomly sets a selected observation.
         */
        selectRandomObservation: function() {
            const randomNumber = Math.floor(Math.random() * 100000);
            this.selectedObservation = this.observationsArray[randomNumber % this.observationsArray.length];
        }
    },
    computed: {
        /**
         * Return the selected observation's ID, or null if no observation is selected.
         *
         * @returns {Number|null} The ID of the selected observation, if one exists.
         */
        getSelectedId: function() {
            if (this.selectedObservation) {
                return this.selectedObservation.id;
            }
            return null
        }
    },
    created: function() {
        this.observationsArray = decodeAndParseJSON(this.schema)['observations'];
        this.allSelectedValues = decodeAndParseJSON(this.observations);
        this.selectRandomObservation();
    },
    mounted: function() {
        this.observer = new ResizeObserver(() => {
            resizeColorbox();
        });

        this.observer.observe(this.$refs.form)
    },
    beforeUnmount: function() {
        if (this.observer) {
            this.observer.disconnect()
        }
    }
}
</script>

<style scoped>
.observation-form {
  padding: .5em;
}
</style>
