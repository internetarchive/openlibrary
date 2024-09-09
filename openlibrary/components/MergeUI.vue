<template>
  <div id="app">
    <MergeTable :olids="olids" :show_diffs="show_diffs" :primary="primary" ref="mergeTable"/>
    <div class="action-bar">
        <div class="comment-input">
            <label for="comment">Comment: </label>
            <input name="comment" v-model="comment" type="text">
        </div>
        <div class="btn-group">
            <button class="merge-btn" @click="doMerge" :disabled="isDisabled">{{mergeStatus}}</button>
            <button class="reject-btn" v-if="showRejectButton" @click="rejectMerge">Reject Merge</button>
        </div>
        <div id="diffs-toggle">
            <label>
                <input type="checkbox" title="Show textual differences" v-model="show_diffs" />
                Show text diffs
            </label>
        </div>
    </div>
    <pre v-if="mergeOutput">{{mergeOutput}}</pre>
  </div>
</template>

<script>
import MergeTable from './MergeUI/MergeTable.vue'
import { do_merge, update_merge_request, createMergeRequest, DEFAULT_EDITION_LIMIT } from './MergeUI/utils.js';

const DO_MERGE = 'Do Merge'
const REQUEST_MERGE = 'Request Merge'
const LOADING = 'Loading...'
const SAVING = 'Saving...'

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
        },
        primary: {
            type: String,
            required: false
        },
        canmerge: {
            type: String,
            required: false,
            default: 'true',
        }
    },
    data() {
        return {
            url: new URL(location.toString()),
            mergeStatus: LOADING,
            mergeOutput: null,
            show_diffs: false,
            comment: ''
        }
    },
    computed: {
        olids() {
            return this.url.searchParams.get('records', '').split(',')
        },

        isSuperLibrarian() {
            return this.canmerge === 'true'
        },

        isDisabled() {
            return this.mergeStatus !== DO_MERGE && this.mergeStatus !== REQUEST_MERGE
        },

        showRejectButton() {
            return this.mrid && this.isSuperLibrarian
        }
    },
    mounted() {
        const readyCta = this.isSuperLibrarian ? DO_MERGE : REQUEST_MERGE
        this.$watch(
            '$refs.mergeTable.merge',
            (new_value) => {
                if (new_value !== undefined && this.mergeStatus === LOADING) this.mergeStatus = readyCta;
            }
        );
    },
    methods: {
        async doMerge() {
            if (!this.$refs.mergeTable.merge) return;
            const { record: master, dupes, editions_to_move, unmergeable_works } = this.$refs.mergeTable.merge;

            this.mergeStatus = SAVING;
            if (this.isSuperLibrarian) {
                // Perform the merge and create new/update existing merge request
                try {
                    if (unmergeable_works.length)
                    {
                        throw new Error(`Could not merge: ${unmergeable_works.join(', ')} has more than ${DEFAULT_EDITION_LIMIT} editions.`);
                    }
                    const r = await do_merge(master, dupes, editions_to_move, this.mrid);
                    if (r.status === 403)
                    {
                        throw new Error('Merge failed, your account may be missing the /usergroup/api permission.');
                    }
                    this.mergeOutput = await r.json();
                    if (this.mrid) {
                        await update_merge_request(this.mrid, 'approve', this.comment)
                    } else {
                        const workIds = [master.key].concat(Array.from(dupes, item => item.key))
                        await createMergeRequest(workIds)
                    }
                } catch (e) {
                    this.mergeOutput = e.message;
                    this.mergeStatus = this.isSuperLibrarian ? DO_MERGE : REQUEST_MERGE;
                    throw e;
                }
            } else {
                // Create a new merge request with "pending" status
                const workIds = [master.key].concat(Array.from(dupes, item => item.key))
                const splitKey = master.key.split('/')
                const primaryRecord = splitKey[splitKey.length - 1]
                await createMergeRequest(workIds, primaryRecord, 'create-pending', this.comment)
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'ok') {
                            // Redirect to merge table on success:
                            window.location.replace(`/merges#mrid-${data.id}`)
                        }
                    })
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
