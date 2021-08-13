<template>
  <div class="observation-form" ref="form">
    <Selections
      :all-selected-values="allSelectedValues"
      :work="work"
      :username="username"
      />

    <!-- Place the following in a box:  -->
    <Categories
      ref="categories"
      :observations-array="capitalizedSchema"
      :all-selected-values="allSelectedValues"
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
      :work="work"
      :username="username"
      />
  </div>
</template>

<script>
import Categories from './ObservationForm/components/Categories'
import Selections from './ObservationForm/components/Selections'
import ValueCard from './ObservationForm/components/ValueCard'

import { decodeAndParseJSON, capitalizeTypesAndValues, capitalizePatronObservations, resizeColorbox } from './ObservationForm/Utils'

export default {
    name: 'ObservationForm',
    components: {
        Categories,
        Selections,
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
        work: {
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
             * An object respresenting the currently selected tag type.
             *
             * @example
             * {
             *   'id': 20,
             *   'label': 'language',
             *   'description': 'What type of verbiage, nomenclature, or symbols are employed in this book?',
             *   'multi_choice': True,
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
             * A version of the schema containing capitalized book tag types and values.
             */
            capitalizedSchema: null,
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
        }
    },
    created: function() {
        this.capitalizedSchema = capitalizeTypesAndValues(decodeAndParseJSON(this.schema)['observations']);
        this.allSelectedValues = capitalizePatronObservations(decodeAndParseJSON(this.observations));
    },
    mounted: function() {
        this.observer = new ResizeObserver(() => {
            resizeColorbox();
        });

        this.observer.observe(this.$refs.form)
    },
    beforeDestroy: function() {
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
