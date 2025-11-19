<template>
  <div class="editions-wrapper">
    <div
      v-if="editions && !editions[record.key].error"
      class="edition-count"
    >
      {{ editions[record.key].size }} edition{{ editions[record.key].size == 1 ? '' : 's' }}
    </div>
    <div
      v-else-if="editions && editions[record.key].error"
      class="edition-count error"
      title="Failed to load editions due to network error"
    >
      editions (error)
    </div>
    <div
      v-else-if="merged && record == merged.record"
      class="edition-count"
    >
      {{ merged.edition_count }} edition{{ merged.edition_count == 1 ? '' : 's' }}
    </div>
    <div
      v-if="editions && !editions[record.key].error"
      class="td-container"
    >
      <EditionSnippet
        v-for="edition in editions[record.key].entries"
        :key="edition.key"
        :edition="edition"
      />
    </div>
  </div>
</template>

<script>
import EditionSnippet from './EditionSnippet.vue';

export default {
    components: {
        EditionSnippet,
    },
    props: {
        record: {
            type: Object,
            required: true
        },
        editions: {
            type: Array,
            required: true
        },
        merged: {
            type: Object,
            required: false
        }
    },
};
</script>

<style lang="less" scoped>
@import (reference) "../../../../../static/css/less/colors.less";

.edition-count.error {
    color: @dark-red;
    font-weight: bold;
}
</style>
