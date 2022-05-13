<template>
    <table>
        <thead>
            <tr>
                <th></th>
                <th v-for="field in fields" :key="field">{{field}}</th>
            </tr>
        </thead>
        <tbody>
            <tr v-for="(role, index) in roles" :key="index">
                <td>{{index}}</td>
                <td v-for="field in fields" :key="field">
                    <div :title="JSON.stringify(role[field])">
                        <div v-if="field == 'type'">
                            {{(role[field].key || role[field]).slice("/type/".length)}}
                        </div>
                        <div v-else-if="field == 'author'">
                            <a :href="`${role[field].key}`" target="_blank">
                                {{role[field].key.slice("/authors/".length)}}
                            </a>
                        </div>
                        <div v-else>{{a[k]}}</div>
                    </div>
                </td>
            </tr>
        </tbody>
    </table>
</template>

<script>
import _ from 'lodash';

export default {
    props: {
        roles: Array
    },
    computed: {
        fields() {
            return _.uniq(_.flatMap(this.roles, Object.keys));
        }
    }
}
</script>
