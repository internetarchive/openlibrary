<template>
  <div class="observation-form">
    <h3>Review this book</h3>
    <Selections
      :all-selected-values="allSelectedValues"
      @remove-value="removeValue"
      />
    <hr>

    <!-- Place the following in a box:  -->
    <Categories
      ref="categories"
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
      />
  </div>
</template>

<script>
import Categories from './ObservationForm/components/Categories'
import Selections from './ObservationForm/components/Selections'
import ValueCard from './ObservationForm/components/ValueCard'

export default {
    name: 'ObservationForm',
    components: {
        Categories,
        Selections,
        ValueCard
    },
    data: function() {
        return {
            selectedObservation: null,
            allSelectedValues: {}
        }
    },
    methods: {
        updateSelected: function(observation) {
            this.selectedObservation = observation
        },
        removeValue: function(type, value) {
            if (this.selectedObservation && this.selectedObservation.label === type) {
                this.$refs['value-card'].$refs['card-body'].toggleChip(value)
            }
        }
    }
}
</script>

<style scoped>
.observation-form {
  padding: .5em;
}
</style>
