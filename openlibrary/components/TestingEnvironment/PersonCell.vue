<script setup>
import { computed } from 'vue';

defineOptions({ name: 'PersonCell' });

const props = defineProps({
    name: {
        type: String,
        default: ''
    },
    avatar: {
        type: String,
        default: ''
    }
});

const initial = computed(() => props.name.charAt(0).toUpperCase());
</script>

<template>
  <span
    v-if="!name"
    class="testing-env__empty"
  >—</span>
  <span
    v-else
    class="testing-env__person"
  >
    <img
      v-if="avatar"
      class="testing-env__avatar"
      :src="avatar"
      width="24"
      height="24"
      :alt="name"
      :title="name"
      loading="lazy"
    >
    <span
      v-else
      class="testing-env__avatar testing-env__avatar--fallback"
      role="img"
      :aria-label="name"
      :title="name"
    >
      {{ initial }}
    </span>
  </span>
</template>
