<template>
  <tr class="work">
    <slot name="pre"></slot>
    <td
      v-for="field in fields"
      :key="field"
      :class="{ [`col-${field.replace(/\|/g, '--')}`]: true }"
    >
      <MergeRowJointField
        v-if="field.includes('|')"
        :fields="field.split('|')"
        :record="record"
        :merged="merged"
        :cellSelected="cellSelected"
      />
      <MergeRowField
        v-else-if="field in record"
        :field="field"
        :value="record[field]"
        :merged="merged"
        :class="{ selected: cellSelected && cellSelected(record, field) }"
      />
    </td>
    <slot name="post"></slot>
  </tr>
</template>

<script>
import MergeRowField from './MergeRowField.vue';
import MergeRowJointField from './MergeRowJointField.vue';

export default {
    components: {
        MergeRowField,
        MergeRowJointField
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
    data() {
        return {
            master_key: null
        };
    }
};
</script>
