<template>
  <div class="card-header">
    <div class="title-line">
      <!-- <h3>{{title}}</h3> -->
    </div>
    <div class="description">{{description}}
      <!-- <span class="close-icon" @click="closeCard">&times;</span> -->
    </div>
  </div>
</template>

<script>
export default {
    name: 'CardHeader',
    props: {
        title: {
            type: String,
            required: true
        },
        description: {
            type: String,
            required: true
        }
    },
    methods: {
        closeCard: function() {
            this.$emit('close-card');
        }
    }
}
</script>

<style scoped>
.card-header {
  border-bottom: 1px solid #999999;
  padding: .5em 1em;
}

.title-line {
  display:flex;
  justify-content: space-between;
  align-items: center;
}

h3, .description {
  margin-left: .25em;
  margin-bottom: 1em;
}

.close-icon {
  font-size: 1.5em;
  margin-right: .25em;
  cursor: pointer;
}
</style>
