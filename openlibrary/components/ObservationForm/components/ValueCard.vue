<template>
  <div class="value-card">
    <CardHeader
      :title="title"
      :description="description"
      />
    <CardBody
      ref="card-body"
      :values="values"
      :multi-select="multiSelect"
      :type="title"
      :all-selected-values="allSelectedValues"
      :work="work"
      :username="username"
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
        },
        allSelectedValues: {
            type: Object,
            required: true
        },
        work: {
            type: String,
            required: true
        },
        username: {
            type: String,
            required: true
        }
    },
}
</script>

<style scoped>
.value-card {
  /* border: 1px solid #999999; */
  border-radius: 4px;
}
</style>
