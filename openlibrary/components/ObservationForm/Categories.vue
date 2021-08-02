<template>
  <div>
    <!-- <h3>Review this book:</h3> -->
    <div class="chip-group">
      <Chip
        v-for="o in observationsArray"
        :key="o.id"
        :ref="'chip' + o.id"
        :text="o.label"
        selectable
        class="category-chip"
        @update-selected="updateSelected"
        />
    </div>
  </div>
</template>

<script>
import { presentableObservations } from '../temp/ObservationService';
import Chip from './Chip.vue'

export default {
    name: 'Categories',
    components: {
        Chip
    },
    data: function() {
        return {
            selected: null,
            observationsArray: null
        }
    },
    methods: {
        updateSelected: function(isSelected, text, toggleSelected) {
            if (isSelected) {
                for (let i = 0; i < this.observationsArray.length; ++i) {
                    if (this.observationsArray[i].label === text) {
                        this.selected = i;
                        this.$emit('update-selected', this.observationsArray[i])
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
                    this.$refs[`chip${id}`][0].toggleSelected()
                }
                this.selected = null;
                this.$emit('update-selected', null)
            }
        }
    },
    beforeMount: function() {
        this.observationsArray = presentableObservations;
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
  margin-bottom: 1em;
}
</style>
