<template>
  <div id="app">
    <MergeTable :olids="olids" ref="mergeTable"/>

    <div class="btn-group">
        <button class="merge-btn" @click="doMerge" :disabled="mergeStatus == 'Saving...'">Do Merge</button>
        <button class="reject-btn" v-if="mrid" @click="rejectMerge">Reject Merge</button>
    </div>
    <div class="comment-input" v-if="mrid">
        <label for="comment">Comment: </label>
        <input name="comment" v-model="comment" type="text">
    </div>
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
    computed: {
        olids() {
            return this.url.searchParams.get('records', '').split(',')
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
                await update_merge_request(this.mrid, 'approve', this.comment)
                this.mergeStatus = `${this.mergeStatus} Merge request closed`
            } catch (e) {
                this.mergeStatus = e.message;
                throw e;
            }
        },

        async rejectMerge() {
            try {
                await update_merge_request(this.mrid, 'decline', this.comment)
                this.mergeStatus = 'Merge request closed'
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
  font-family: Roboto;
}

.btn-group {
    display: flex;
    justify-content: space-between;
    margin-bottom: 5px;
    padding: 5px;

    .merge-btn {
        background-color: green;
    }

    .reject-btn {
        background-color: red;
    }
}

.comment-input {
    padding: 0 5px 5px;

    input {
        width: 90%;
    }
}
</style>
