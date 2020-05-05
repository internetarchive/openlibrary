<template>
  <div id="app">
    <MergeTable :olids="url.searchParams.get('records', '').split(',')" ref="mergeTable"/>

    <button @click="doMerge">Do Merge</button>
  </div>
</template>

<script>
import MergeTable from './MergeUI/MergeTable.vue'
import { do_merge } from './MergeUI/utils.js';

export default {
    name: 'app',
    components: {
        MergeTable
    },
    data() {
        return {
            url: new URL(location.toString())
        }
    },
    methods: {
        doMerge() {
            if (!this.$refs.mergeTable.merge) return;
            const { record: master, dupes, editions_to_move } = this.$refs.mergeTable.merge;

            do_merge(master, dupes, editions_to_move);
        }
    }
}
</script>

<style>
#app {
  font-family: Roboto;
}
</style>
