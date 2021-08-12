<template>
  <div>
    <h3>Add your reviews:</h3>
    <div class="chip-group">
      <Chip
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
      </Chip>
    </div>
  </div>
</template>

<script>
import Chip from './Chip.vue'

export default {
    name: 'Categories',
    components: {
        Chip
    },
    props: {
        observationsArray: {
            type: Array,
            required: true
        },
        allSelectedValues: {
            type: Object,
            required: true
        }
    },
    data: function() {
        return {
            selectedId: null,
        }
    },
    methods: {
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
                this.selected = null;

                // Set ObservationForm's selected observation to null
                this.$emit('update-selected', null)
            }
        },
        isSelected: function(id) {
            return this.selectedId === id
        },
        displaySymbol: function(type) {
            // &#10133; - Heavy plus
            // &#10004; - Heavy checkmark
            if (this.allSelectedValues[type] && this.allSelectedValues[type].length) {
                return '&#10004;';
            }
            return '&#10133;';
        }
    }
}
</script>

<style scoped>
.chip-group {
  display: flex;
  flex-wrap: wrap;
}
.category-chip {
  margin-right: 1em;
  margin-bottom: .5em;
}

</style>
