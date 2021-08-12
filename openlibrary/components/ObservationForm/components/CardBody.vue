<template>
  <div class="card-body">
    <Chip
      v-for="item in values"
      :key="item + type"
      :text="item"
      :ref="'chip-' + item"
      selectable
      :selected="selectedValues.includes(item)"
      class="value-chip"
      @update-selected="updateSelected"
      />
  </div>
</template>

<script>
import Vue from 'vue'

import Chip from './Chip'

import { deleteObservation, addObservation } from '../ObservationService'

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
    methods: {
        updateSelected: function(isSelected, text) {
            let updatedValues = this.allSelectedValues[this.type] ? this.allSelectedValues[this.type] : []

            if (isSelected) {
                if (this.multiSelect) {
                    updatedValues.push(text)
                } else {
                    if (updatedValues.length) {
                        deleteObservation(this.type, updatedValues[0], this.work, this.username)
                    }
                    updatedValues = [text]
                }

                addObservation(this.type, text, this.work, this.username);
                Vue.set(this.allSelectedValues, this.type, updatedValues);
            } else {
                const index = updatedValues.indexOf(text);
                updatedValues.splice(index, 1);
                deleteObservation(this.type, text, this.work, this.username)
            }
        }
    },
    computed: {
        selectedValues: function() {
            return this.allSelectedValues[this.type]?.length ? this.allSelectedValues[this.type] : []
        }
    }
}
</script>

<style scoped>
.card-body {
  display: flex;
  flex-wrap: wrap;
  padding: 1em;
}

.value-chip {
  margin-right: 1em;
  margin-bottom: .5em;
}
</style>
