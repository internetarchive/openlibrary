<template>
  <div class="selections" v-show="selectedValues.length">
    <!-- <h3>Selections:</h3> -->
    <div
      v-if="!selectedValues.length"
      class="no-selections-message"
      >
      No tags selected.
    </div>
    <div
      v-else
      class="selection-panel"
      >
        <Chip
          v-for="value in selectedValues"
          :key="value"
          :text="value"
          :ref="value"
          class="selection-chip"
          >
          <span
            class="close-icon"
            title="Remove value"
            @mouseover="addHoverClass(value)"
            @mouseout="removeHoverClass(value)"
            @click="removeItem(value)">&times;</span>
        </Chip>
      </div>
  </div>
</template>

<script>
import Chip from '@/components/Chip'
// import { mapGetters, mapMutations } from 'vuex';

export default {
    name: 'Selections',
    components: {
        Chip
    },
    methods: {
        // ...mapMutations(['REMOVE_VALUE']),
        removeItem: function(itemText) {
            const splitText = itemText.split(': ')
            this.REMOVE_VALUE({
                type: splitText[0],
                value: splitText[1]
            });
            this.$emit('remove-value', splitText[0], splitText[1])
        },
        addHoverClass: function(ref) {
            this.$refs[ref][0].$el.classList.add('hover')
        },
        removeHoverClass: function(ref) {
            this.$refs[ref][0].$el.classList.remove('hover')
        }
    },
    computed: {
        // ...mapGetters(['selectedValues'])
    }
}
</script>

<style scoped>
/* .selections {
  border: 1px solid #999999;
} */
.no-selections-message {
  margin-bottom: 1em;
}

.selection-panel {
  display: flex;
  flex-wrap: wrap;
}

.selection-chip {
  margin-right: 1em;
  margin-top: 1em;  /* TODO: fix padding */
  margin-bottom: 1em;
}

.close-icon {
  cursor: pointer;
}

.hover {
  border-color: red;
  color: red;
}
</style>
