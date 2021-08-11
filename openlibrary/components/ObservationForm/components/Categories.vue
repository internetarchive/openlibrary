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
            selected: null,
        }
    },
    methods: {
        updateSelected: function(isSelected, text, toggleSelected) {
            if (isSelected) {
                for (let i = 0; i < this.observationsArray.length; ++i) {
                    if (this.observationsArray[i].label === text) {
                        this.selected = i;
                        // TODO: event
                        this.$emit('update-selected', this.observationsArray[i])
                        // TODO: refs:
                    } else if (this.$refs[`chip${this.observationsArray[i].id}`][0].isSelected){
                        this.$refs[`chip${this.observationsArray[i].id}`][0].toggleSelected();
                    }
                }
            } else {
                if (toggleSelected) {
                    let id;

                    for (let i = 0; i < this.observationsArray.length; ++i) {
                        if (this.observationsArray[i].label === text) {
                            id = this.observationsArray[i].id
                            break;
                        }
                    }
                    // TODO: refs
                    this.$refs[`chip${id}`][0].toggleSelected()
                }
                this.selected = null;

                // Set ObservationForm's selected observation to null
                this.$emit('update-selected', null)
            }
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
