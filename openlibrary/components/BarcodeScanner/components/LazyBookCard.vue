<template>
  <a class="lazy-book-card" :href="state.link">
    <div class="cover">
      <img :src="state.coverSrc">
    </div>
    <div class="info">
      <div class="title">{{ state.title }}</div>
      <div class="byline">{{ state.byline }}</div>
      <div class="identifier">{{ state.identifier }}</div>
    </div>
  </a>
</template>

<script>

export default {
    props: {
        isbn: {
            type: String || null,
        },
        state: {
            type: null
        },
    },
}
</script>
