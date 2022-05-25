<template>
  <div id="app">
    <MergeTable
        :olids="url.searchParams.get('records', '').split(',')"
        :show_diffs="show_diffs"
        ref="mergeTable"
        />
    <button @click="doMerge" :disabled="mergeStatus == 'Saving...'">Do Merge</button>
    <div id="diffs-toggle"><input type="checkbox" id="diff-checkbox" title="Show textual differences" v-model="show_diffs" />
    <label for="diff-checkbox">Show text diffs</label></div>
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
            mergeStatus: null,
            show_diffs: false
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

<style lang="less">
#app {
    font-size: 0.9em;

    & > button {
        font-size: 1.3em;
        padding: 5px;
        margin: 5px;
    }

    div#diffs-toggle {
        float: right;
        padding: 4px 8px 0 0;
    }
}
</style>
