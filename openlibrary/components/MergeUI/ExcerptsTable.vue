<template>
    <ul class="reset">
        <li class="excerpt-item" v-for="(excerpt, index) in excerpts" :key="index">
                <span v-if="excerpt['excerpt']" :title="`excerpt-${index}`">
                    {{excerpt['excerpt'].value || excerpt['excerpt']}}
                </span>
                <span v-if="excerpt['pages']">
                    (page: {{excerpt['pages']}})
                </span>
                <span v-if="excerpt['page']">
                    (page: {{excerpt['page']}})
                </span>
                <span v-if="excerpt['author']">
                    <a :href="excerpt['author'].key" target="_blank">
                        {{excerpt['author'].key.slice("/people/".length)}}
                    </a>
                </span>
        </li>
    </ul>
</template>

<script>
import _ from 'lodash';

export default {
  props: {
    excerpts: Array
  },
  computed: {
    fields() {
      return _.uniq(_.flatMap(this.excerpts, Object.keys));
    }
  }
}
</script>
