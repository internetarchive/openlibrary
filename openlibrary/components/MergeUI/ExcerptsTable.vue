<template>
    <table>
        <thead>
            <tr>
            <th></th>
            <th v-for="field in fields" :key="field">{{field}}</th>
            </tr>
        </thead>
    <tbody>
        <tr v-for="(excerpt, index) in excerpts" :key="index">
            <td>{{index}}</td>
            <td v-for="field in fields" :key="field">
            <div v-if="excerpt[field] == 'excerpt'" :title="excerpt[field]">
                {{excerpt[field].value || excerpt[field]}}
            </div>
            <div v-if="excerpt[field] == 'author'">
                <a :href="excerpt[field].key" target="_blank">
                    {{excerpt[field].key.slice("/people/".length)}}
                </a>
            </div>
            <div v-else>{{excerpt[field]}}</div>
        </td>
        </tr>
    </tbody>
    </table>
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
