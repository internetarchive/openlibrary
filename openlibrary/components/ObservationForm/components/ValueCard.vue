<template>
  <div class="value-card">
    <CardHeader
      :description="description"
      />
    <CardBody
      ref="card-body"
      :values="values"
      :multi-select="multiSelect"
      :type="type"
      :all-selected-values="allSelectedValues"
      :work-key="workKey"
      :username="username"
      />
  </div>
</template>

<script>
import CardBody from './CardBody.vue'
import CardHeader from './CardHeader.vue';

export default {
    name: 'ValueCard',
    components: {
        CardHeader,
        CardBody
    },
    props: {
        /**
         * A question clarifying the currently selected book tag type.
         */
        description: {
            type: String,
            required: true
        },
        /**
         * The currently selected book tag type.
         */
        type: {
            type: String,
            required: true
        },
        /**
         * Whether or not multiple values can be selected for the current book tag type.
         */
        multiSelect: {
            type: Boolean,
            required: false,
            default: false
        },
        /**
         * All possible values for the current book tag type.
         */
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
        /**
         * An object containing all of the patron's currently selected book tags.
         *
         * @example
         * {
         *   "mood": ["joyful"],
         *   "genres": ["sci-fi", "anthology"]
         * }
         */
        allSelectedValues: {
            type: Object,
            required: true
        },
        /**
         * The work key.
         *
         * @example
         * /works/OL123W
         */
        workKey: {
            type: String,
            required: true
        },
        /**
         * The patron's username.
         */
        username: {
            type: String,
            required: true
        }
    },
}
</script>

<style scoped>
.value-card {
  border: 1px solid #999999;
  border-radius: 4px;
  margin: 1em 3em;
}

@media (max-width: 768px) {
    .value-card {
        margin: unset;
    }
}

</style>
