<template>
  <ul class="reset">
    <li
      v-for="(excerpt, index) in excerpts"
      :key="index"
      class="excerpt-item"
    >
      <span
        v-if="excerpt['excerpt']"
        :title="`excerpt-${index}`"
      >
        {{ excerpt['excerpt'].value || excerpt['excerpt'] }}
      </span>
      <span v-if="excerpt['pages']">
        (page: {{ excerpt['pages'] }})
      </span>
      <span v-if="excerpt['page']">
        (page: {{ excerpt['page'] }})
      </span>
      <span v-if="excerpt['author']">
        <a
          :href="excerpt['author'].key"
          target="_blank"
        >
          {{ excerpt['author'].key.slice("/people/".length) }}
        </a>
      </span>
    </li>
  </ul>
</template>

<script>
export default {
    props: {
        excerpts: {
            type: Array,
            default: () => []
        }
    },
    computed: {
        fields() {
            return [...new Set(this.excerpts.flatMap(excerpt => Object.keys(excerpt)))];
        }
    }
};
</script>
