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
      :title="selectedObservation.label"
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

import { deleteObservation } from './ObservationForm/ObservationService'
import { decodeAndParseJSON, capitalizeTypesAndValues, capitalizePatronObservations, resizeColorbox } from './ObservationForm/Utils'

export default {
    name: 'ObservationForm',
    components: {
        Categories,
        Selections,
        ValueCard
    },
    props: {
        schema: {
            type: String,
            required: true
        },
        observations: {
            type: String,
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
            selectedObservation: null,
            allSelectedValues: {},
            capitalizedSchema: null,
        }
    },
    methods: {
        updateSelected: function(observation) {
            this.selectedObservation = observation
        },
        removeValue: function(type, value) {
            deleteObservation(type, value, this.work, this.username);
            if (this.selectedObservation && this.selectedObservation.label === type) {
                this.$refs['value-card'].$refs['card-body'].toggleChip(value)
            }
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
