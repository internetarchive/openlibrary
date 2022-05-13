<template>
  <div>
    <MergeRowField
      v-for="field in presentFields"
      :key="field"
      :field="field"
      :value="record[field]"
      :merged="merged"
      :class="{ selected: cellSelected && cellSelected(record, field) }"
    />
  </div>
</template>

<script>
import MergeRowField from './MergeRowField.vue';

export default {
    components: {
        MergeRowField
    },
    props: {
        record: {
            type: Object,
            required: true
        },
        fields: {
            type: Array,
            required: true
        },
        cellSelected: {
            type: Function
        },
        merged: {
            type: Object,
            required: false
        }
    },
    computed: {
        presentFields() {
            return this.fields.filter(f => f in this.record);
        }
    }
};
</script>
