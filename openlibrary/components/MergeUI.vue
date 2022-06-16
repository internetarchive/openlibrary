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
import { do_merge, update_merge_request } from './MergeUI/utils.js';

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
                // const r = await do_merge(master, dupes, editions_to_move);
                // this.mergeStatus = await r.json();
                await update_merge_request(this.mrid, 'approve', this.comment)
                this.mergeStatus = this.mergeStatus + " Merge request closed"
            } catch (e) {
                this.mergeStatus = e.message;
                throw e;
            }
        },

        async rejectMerge() {
            try {
                const r = await update_merge_request(this.mrid, 'decline', this.comment)
                this.mergeStatus = "Merge request closed"
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
