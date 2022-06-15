<template>
  <div id="app">
    <MergeTable :olids="url.searchParams.get('records', '').split(',')" ref="mergeTable"/>

    <button @click="doMerge" :disabled="mergeStatus == 'Saving...'">Do Merge</button>
    <span v-if="mrid">
        <button @click="rejectMerge">Reject Merge</button>
        <label for="comment">Comment: </label>
        <input name="comment" v-model="comment" type="text">
    </span>
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
    props: {
        mrid: {
            type: [Number, String],
            required: false,
            default: ''
        }
    },
    data() {
        return {
            url: new URL(location.toString()),
            mergeStatus: null,
            comment: ''
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
        },

        rejectMerge() {
            console.log('rejected')
        }
    }
}
</script>

<style>
#app {
  font-family: Roboto;
}
</style>
