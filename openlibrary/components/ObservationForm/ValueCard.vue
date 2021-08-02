<template>
  <div class="value-card">
    <CardHeader
      :title="title"
      :description="description"
      @close-card="closeCard"
      />
    <CardBody
      ref="card-body"
      :values="values"
      :multi-select="multiSelect"
      :type="title"
      />
  </div>
</template>

<script>
import CardBody from './CardBody'
import CardHeader from './CardHeader';

export default {
    name: 'ValueCard',
    components: {
        CardHeader,
        CardBody
    },
    props: {
        title: {
            type: String,
            required: true
        },
        description: {
            type: String,
            required: true
        },
        multiSelect: {
            type: Boolean,
            required: false,
            default: false
        },
        values: {
            type: Array,
            required: true,
            validator: function(arr) {
                for (const item of arr) {
                    if (typeof(item) !== 'string') {
                        return false;
                    }
                }
                return true;
            }
        }
    },
    methods: {
        closeCard: function() {
            this.$emit('close-card')
        }
    }
}
</script>

<style scoped>
.value-card {
  /* border: 1px solid #999999; */
  border-radius: 4px;
}
</style>
