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
        :class="{ [`wrap-${field.replace(/\|/g, '--')}`]: true }"
        :show_diffs="show_diffs"
      />
      <MergeRowField
        v-else-if="field in record"
        :field="field"
        :value="record[field]"
        :merged="merged"
        :class="{ selected: cellSelected && cellSelected(record, field) }"
        :show_diffs="show_diffs"
      />
      <MergeRowEditionField
        v-else-if="field == 'editions'"
        :editions="editions"
        :record="record"
        :merged="merged"
        :class="{ selected: cellSelected && cellSelected(record, field) }"
      />
      <MergeRowReferencesField
        v-else-if="field == 'references'"
        :lists="lists"
        :bookshelves="bookshelves"
        :ratings="ratings"
        :record="record"
        :merged="merged"
        :class="{ selected: cellSelected && cellSelected(record, field) }"
      />
    </td>
  </tr>
</template>

<script>
import MergeRowField from './MergeRowField.vue';
import MergeRowJointField from './MergeRowJointField.vue';
import MergeRowEditionField from './MergeRowEditionField.vue';
import MergeRowReferencesField from './MergeRowReferencesField.vue';

export default {
  components: {
    MergeRowField,
    MergeRowJointField,
    MergeRowEditionField,
    MergeRowReferencesField
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
    editions: {
      type: Array,
    },
    lists: {
      type: Object,
    },
    bookshelves: {
      type: Object,
    },
    ratings: {
      type: Object,
    },
    cellSelected: {
      type: Function
    },
    merged: {
      type: Object,
      required: false
    },
    show_diffs: {
      type: Boolean
    }
  },
  data() {
    return {
      master_key: null
    };
  }
};
</script>
