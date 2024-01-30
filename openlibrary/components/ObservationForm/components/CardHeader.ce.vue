<template>
  <div class="card-header">
    <div class="description">{{description}}</div>
  </div>
</template>

<script>
export default {
    name: 'CardHeader',
    props: {
        /**
         * A question clarifying the currently selected book tag type.
         */
        description: {
            type: String,
            required: true
        }
    },
}
</script>

<style>
.card-header {
  border-bottom: 1px solid #999;
  margin: 1em;
  padding-bottom: 1em;
}
</style>
