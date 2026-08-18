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
      v-if="avatarUrl"
      class="testing-env__avatar"
      :src="avatarUrl"
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
    >{{ initial }}</span>
  </span>
</template>

<script>
import { safeHttpUrl } from './utils.js';

export default {
    name: 'PersonCell',
    props: {
        name: {
            type: String,
            default: ''
        },
        avatar: {
            type: String,
            default: ''
        }
    },
    computed: {
        avatarUrl() {
            return safeHttpUrl(this.avatar);
        },
        initial() {
            return this.name.charAt(0).toUpperCase();
        }
    }
};
</script>
