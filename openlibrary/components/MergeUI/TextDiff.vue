<template>
    <div v-if="show_diffs">
        <span v-for="(part, i) in diff" :key="i" :class="part">{{part.value}}</span>
    </div>
    <div v-else>
        {{left}}
    </div>
</template>

<script>
import {diffChars, diffWordsWithSpace} from 'diff';

export default {
    props: {
        left: String,
        right: String,
        show_diffs: Boolean,
        resolution: {
            default: 'char',
            validator: val => ['char', 'word'].includes(val),
        }
    },
    computed: {
        diff() {
            const fn = {
                char: diffChars,
                word: diffWordsWithSpace,
            };
            return fn[this.resolution](this.left, this.right);
        }
    }
}
</script>

<style scoped>
.value { background: rgba(0,0,255, .1); }
.added { color: green; background: rgba(0,255,0, .1); }
.removed { color: red; text-decoration: line-through; background: rgba(255,0,0, .1); user-select: none; }
</style>
