<template>
    <div>
        <div class="label"><label for="name">Identifiers</label></div>
        <div class="allButHeader">
            <div id="identifiers-display">
                <div class="wrapper">
                    <span class="box">
                        <select v-model="selected" name="name" id="select-id" aria-invalid="false">
                            <option disabled value="">Select one of many...</option>
                            <option v-for="item in allIdentifiers" :key="item.name" :value="item.name">{{item.label}}</option>
                        </select>
                    </span>
                    <span class="box">
                        <input type="text" name="value" id="id-value" v-model="inputValue" aria-invalid="false">
                        <button type="button" name="add" :disabled="this.selected == ''" @click=clickSet>Set</button>
                    </span>
                    <template v-for="(item) in identifiersWithValues">
                        <div class="box" :key="item.name">{{ item.label }}</div>
                        <div class="box" :key="item.name">{{ item.value }}</div>
                    </template>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    // Props are for external options; if a subelement of this is modified,
    // the view automatically re-renders
    props: {
        // these are the remote ids with associated values, a subset of all identifieirs
        remote_ids_string: {
            type: String,
            //default: () =>  '{"wikidata": "Q10000"}'
        },
        // these are eventually going to be passed in from the config, a list of all possible ids
        allIdentifiers: {
            type: Array,
            default: () => [
                {
                    name: 'wikidata',
                    label: 'Wikidata'
                },
                {
                    name: 'viaf',
                    label: 'VIAF'
                },
                {
                    name: 'isni',
                    label: 'ISNI'
                }
            ],
        },
    },

    // Data is for internal stuff. This needs to be a function so that we get
    // a fresh object every time this is initialized.
    data: () => {
        return {
            selected: '', // Which identifier is selected in dropdown
            inputValue: '', // What user put into input
            remote_ids_parsed: {},
            all_ids_by_key: {}
        }
    },

    computed: {
        // Merges the key/value with the config data about identifiers
        identifiersWithValues: function(){
            return Object.entries(this.remote_ids_parsed)
                .map(([key, value]) => Object.assign(this.all_ids_by_key[key], {value: value}));
        }
    },

    methods: {
        clickSet: function(){
            // We use $set otherwise we wouldn't get the reactivity desired
            // See https://vuejs.org/v2/guide/reactivity.html#Change-Detection-Caveats
            this.$set(this.remote_ids_parsed, this.selected, this.inputValue)
            this.inputValue = '';

            // TODO: I'm not sure how to get around this
            // Right now, we have a vue component embeded as a small part of a larger form
            // As far as I can tell, there is no way for that parent form to automatically detect the inputs in a component without JS
            // This is because the vue component is in a shadow dom
            // So for now this just drops the hidden inputs into the the parent form anytime there is a change
            const html = this.identifiersWithValues.map(item=>`<input type="hidden" name="author--remote_ids--${item.name}" value="${item.value}"/>`).join('');
            document.querySelector('#hiddenIdentifierInputs').innerHTML = html;
        },
    },
    mounted: function(){
        // TODO: figue out how to pass valid JSON so we don't need this hack
        this.remote_ids_parsed = JSON.parse(this.remote_ids_string.replace(/'/g, '"'));
        this.allIdentifiers.forEach(element=>this.all_ids_by_key[element.name] = element);
    }
}
</script>

<style lang="less">
.wrapper {
  display: grid;
  grid-template-columns: 20% auto;
  grid-row-gap: 1px;
  background-color: #ddd;
}
.box {
  padding: .5rem;
  background-color: #f6f5ee;
}
label {
    font-size: 1em;
    font-family: "Lucida Grande","Trebuchet MS",Geneva,Helvetica,Arial,sans-serif;
    font-weight: 700;
}
.allButHeader {
    background-color: #f6f5ee;
}
#select-id {
    width: 100%;
}
button {
    margin-left: 1rem;
}
input, select, button {
    padding: 3px;
    font-size: 1.125rem;
}
</style>
