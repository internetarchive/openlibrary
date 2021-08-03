<template>
  <div class="card-body">
    <Chip
      v-for="item in values"
      :key="item + type"
      :text="item"
      :ref="'chip-' + item"
      selectable
      :selected="isSelected(item)"
      class="value-chip"
      @update-selected="updateSelected"
      />
  </div>
</template>

<script>
import Vue from 'vue'

import Chip from './Chip'

export default {
    name: 'CardBody',
    components: {
        Chip
    },
    props: {
        values: {
            type: Array,
            required: true
        },
        multiSelect: {
            type: Boolean,
            required: false,
            default: false,
        },
        type: {
            type: String,
            required: true
        },
        allSelectedValues: {
            type: Object,
            required: true
        }
    },
    methods: {
        updateSelected: function(isSelected, text) {
            const updatedValues = this.allSelectedValues[this.type] ? this.allSelectedValues[this.type] : []

            if (isSelected) {
                for (let i = 0; i < this.values.length; ++i) {
                    if (this.values[i] === text) {
                        updatedValues.push(text);
                    } else if (!this.multiSelect) {
                        const ref = `chip-${this.values[i]}`;
                        if (this.$refs[ref][0].isSelected) {
                            const index = updatedValues.indexOf(this.values[i]);

                            updatedValues.splice(index, 1);
                            this.$refs[ref][0].toggleSelected()
                        }
                    }
                }
            } else {
                const index = updatedValues.indexOf(text);

                updatedValues.splice(index, 1);
            }

            Vue.set(this.allSelectedValues, this.type, updatedValues);
        },
        toggleChip: function(text) {
            const ref = `chip-${text}`
            this.$refs[ref][0].toggleSelected()
        },
        isSelected: function(value) {
            if (!this.allSelectedValues[this.type]) {
                return false;
            }
            return this.allSelectedValues[this.type].indexOf(value) !== -1;
        }
    }
}
</script>

<style scoped>
.card-body {
  margin: 1em .25em 0;
  display: flex;
  flex-wrap: wrap;
  padding: .5em 1em;
}

.value-chip {
  margin-right: 1em;
  margin-bottom: 1em;
}
</style>
