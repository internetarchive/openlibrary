<template>
  <div id="app">
    <MergeTable :olids="olids" :show_diffs="show_diffs" ref="mergeTable"/>
    <div class="action-bar">
        <div class="comment-input" v-if="mrid">
            <label for="comment">Comment: </label>
            <input name="comment" v-model="comment" type="text">
        </div>
        <div class="btn-group">
            <button class="merge-btn" @click="doMerge" :disabled="mergeStatus != 'Do Merge'">{{mergeStatus}}</button>
            <button class="reject-btn" v-if="mrid" @click="rejectMerge">Reject Merge</button>
        </div>
        <div id="diffs-toggle">
        <label>
            <input type="checkbox" title="Show textual differences" v-model="show_diffs" />
            Show text diffs
        </label>
    </div>
    <pre v-if="mergeOutput">{{mergeOutput}}</pre>
  </div>
</template>

<script>
import MergeTable from './MergeUI/MergeTable.vue'
import { do_merge, update_merge_request, createMergeRequest, DEFAULT_EDITION_LIMIT } from './MergeUI/utils.js';

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
            mergeStatus: 'Loading...',
            mergeOutput: null,
            show_diffs: false,
            comment: ''
        }
    },
    computed: {
        olids() {
            return this.url.searchParams.get('records', '').split(',')
        }
    },
    mounted() {
        this.$watch(
            '$refs.mergeTable.merge',
            (new_value, old_value) => {
                if (new_value && new_value !== old_value) this.mergeStatus = 'Do Merge';
            }
        );
    },
    methods: {
        async doMerge() {
            if (!this.$refs.mergeTable.merge) return;
            const { record: master, dupes, editions_to_move, unmergeable_works } = this.$refs.mergeTable.merge;

            this.mergeStatus = 'Saving...';
            try {
                if (unmergeable_works.length)
                {
                    throw new Error(`Could not merge: ${unmergeable_works.join(', ')} has more than ${DEFAULT_EDITION_LIMIT} editions.`);
                }
                const r = await do_merge(master, dupes, editions_to_move, this.mrid);
                this.mergeOutput = await r.json();
                if (this.mrid) {
                    await update_merge_request(this.mrid, 'approve', this.comment)
                } else {
                    const workIds = [master.key].concat(Array.from(dupes, item => item.key))
                    await createMergeRequest(workIds)
                }
            } catch (e) {
                this.mergeOutput = e.message;
                this.mergeStatus = 'Do Merge';
                throw e;
            }
            this.mergeStatus = 'Done';
        },

        async rejectMerge() {
            try {
                await update_merge_request(this.mrid, 'decline', this.comment)
                this.mergeOutput = 'Merge request closed'
            } catch (e) {
                this.mergeOutput = e.message;
                throw e;
            }
            this.mergeStatus = 'Reject Merge';
        }
    }
}
</script>

<style lang="less">
#app {
    font-size: 0.9em;

    div#diffs-toggle {
        float: right;
        padding: 4px 8px 0 0;
    }
}

.btn-group {
    display: flex;
    justify-content: space-between;
    margin-bottom: 5px;
    padding: 5px;

    & > button {
        font-size: 1.3em;
        padding: 10px;
        margin: 5px;
        border: none;
        border-radius: 5px;
        color: white;
    }

    .merge-btn {
        background-color: rgb(76, 118, 76);
    }
    .merge-btn:hover {
        background-color: rgb(100, 156, 100);
    }

    .merge-btn[disabled] {
        background-color: rgb(117, 117, 117);
    }
    .merge-btn[disabled]:hover {
        background-color: rgb(117, 117, 117);
    }
    .reject-btn {
        background-color: rgb(125, 43, 43);
    }
    .reject-btn:hover {
        background-color: rgb(161, 56, 56);
    }
}

.comment-input {
    display: flex;
    flex-direction: column;
    padding: 0 5px 5px 10px;

    input {
        width: 90%;
    }
}

.action-bar {
    margin: 5px;
}
</style>
