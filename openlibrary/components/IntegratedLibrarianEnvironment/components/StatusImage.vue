<template>
  <li>
    <img :title="titleData" :src="imageData">
  </li>
</template>

<script>
export default {
    props: {
        title: {
            type: String,
        },
        image: {
            type: String,
            default: null,
        }
    },
    data() {
        return {
            titleData: this.title,
            imageData: this.image,
        }
    },
}
</script>

<style lang="less">

li:first-child {
  flex-shrink: 0;
}

img {
  max-width: 100%;
  height: 80px;
  object-fit: cover;
  object-position: right;
}
</style>
