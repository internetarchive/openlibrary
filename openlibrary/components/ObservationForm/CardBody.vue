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
import Chip from './Chip'
// import {mapMutations, mapState, mapGetters } from 'vuex';

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
        }
    },
    computed: {
        // ...mapState(['selected']),
        // ...mapGetters(['indexOfValue']),
        selectedValues() {
            return this.selected[this.type] ? this.selected[this.type] : []
        }
    },
    methods: {
        // ...mapMutations(['UPDATE_SELECTED']),
        updateSelected: function(isSelected, text) {
            if (isSelected) {
                for (let i = 0; i < this.values.length; ++i) {
                    if (this.values[i] === text) {
                        this.selectedValues.push(text);
                    } else if (!this.multiSelect) {
                        const ref = `chip-${this.values[i]}`;
                        if (this.$refs[ref][0].isSelected) {
                            const index = this.selectedValues.indexOf(this.values[i]);

                            this.selectedValues.splice(index, 1);
                            this.$refs[ref][0].toggleSelected()
                        }
                    }
                }
            } else {
                const index = this.selectedValues.indexOf(text);

                this.selectedValues.splice(index, 1);
            }
            this.UPDATE_SELECTED({
                type: this.type,
                selected: this.selectedValues
            })
        },
        toggleChip: function(text) {
            const ref = `chip-${text}`
            this.$refs[ref][0].toggleSelected()
        },
        isSelected: function(value) {
            return this.indexOfValue(this.type, value) !== -1;
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
