<template>
  <div id="app">
    <MergeTable :olids="url.searchParams.get('records', '').split(',')" ref="mergeTable"/>

    <button @click="doMerge" :disabled="mergeStatus == 'Saving...'">Do Merge</button>
    <pre v-if="mergeStatus">{{mergeStatus}}</pre>
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
            url: new URL(location.toString()),
            mergeStatus: null
        }
    },
    methods: {
        async doMerge() {
            if (!this.$refs.mergeTable.merge) return;
            const { record: master, dupes, editions_to_move } = this.$refs.mergeTable.merge;

            this.mergeStatus = 'Saving...';
            try {
                const r = await do_merge(master, dupes, editions_to_move);
                this.mergeStatus = await r.json();
            } catch (e) {
                this.mergeStatus = e.message;
                throw e;
            }
        }
    }
}
</script>

<style>
#app {
  font-family: Roboto;
}
</style>
