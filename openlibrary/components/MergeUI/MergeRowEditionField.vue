<template>
    <div class="editions-wrapper">
        <div class="edition-count" v-if="editions">
            {{editions[record.key].size}} edition{{editions[record.key].size == 1 ? '' : 's'}}
        </div>
        <div class="edition-count" v-else-if="merged && record == merged.record">
            {{merged.edition_count}} edition{{merged.edition_count == 1 ? '' : 's'}}
        </div>
        <div class="td-container" v-if="editions">
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
