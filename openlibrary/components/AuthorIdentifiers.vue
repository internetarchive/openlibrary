<template>
    <div class="wrapper">
        <span class="box">
            <select v-model="selected" name="name">
                <option disabled value="">Select one</option>
                <option v-for="identifier in allIdentifiers" :key="identifier.name" :value="identifier.name">
                  {{identifier.label}}
                </option>
            </select>
        </span>
        <span class="box">
            <input type="text" name="value" id="id-value" v-model="inputValue" @keyup.enter=setIdentifier>
        </span>
        <span class="box">
            <button type="button" name="set" :disabled="!setButtonEnabled" @click=setIdentifier>Set</button>
        </span>
        <template v-for="identifier in identifiersWithValues">
            <div class="box" :key="identifier.name">{{ identifier.label }}</div>
            <div class="box" :key="identifier.name">{{ identifier.value }}</div>
            <div class="box" :key="identifier.name">
                <button type="button" @click="removeIdentifier(identifier.name)">Remove</button>
            </div>
        </template>
    </div>
</template>

<script>
export default {
    // Props are for external options; if a subelement of this is modified,
    // the view automatically re-renders
    props: {
        // this is the list of remote ids currently associated with the book in the database
        // It is passed as a string and then converted to json
        remote_ids_string: {
            type: String,
            //default: () =>  "{'wikidata': 'Q10000'}"
        },
        // these are eventually going to be passed in from the config, a list of all possible ids
        allIdentifiers: {
            type: Array,
            default: () => []
        },
        // see createHiddenInputs function for usage
        output_selector: {
            type: String,
        }
    },

    // Data is for internal stuff. This needs to be a function so that we get
    // a fresh object every time this is initialized.
    data: () => {
        return {
            selectedIdentifier: '', // Which identifier is selected in dropdown
            inputValue: '', // What user put into input
            remoteIdsParsed: {}, // IDs assigned to object in client
        }
    },

    computed: {
        // Merges the key/value with the config data about identifiers
        identifiersWithValues: function(){
            return Object.entries(this.remoteIdsParsed)
                .map(([key, value]) => Object.assign(this.allIdentifiersByKey[key] || {}, {value: value}));
        },
        // allows for lookup of identifier in O(1) time
        allIdentifiersByKey: function(){
            const out = {}
            this.allIdentifiers.forEach(element=>out[element.name] = element);
            return out;
        },
        setButtonEnabled: function(){
            return this.selected !== '' && this.inputValue !== '';
        }
    },

    methods: {
        setIdentifier: function(){
            // if no identifier selected don't execute
            if (!this.setButtonEnabled) return

            // We use $set otherwise we wouldn't get the reactivity desired
            // See https://vuejs.org/v2/guide/reactivity.html#Change-Detection-Caveats
            this.$set(this.remoteIdsParsed, this.selected, this.inputValue)
            this.inputValue = '';
            this.createHiddenInputs()
        },
        // Removes an identifier with value from memory and it will be deleted from database on save
        removeIdentifier: function(identifierName){
            this.$set(this.remoteIdsParsed, identifierName, '')
            this.createHiddenInputs()
        },
        fetchAllIdentifiers: async function(){
            const responseJson = await fetch('/config/author.json')
                .then(response => response.json());
            this.allIdentifiers = responseJson.identifiers
        },
        createHiddenInputs: function(){
            // Right now, we have a vue component embedded as a small part of a larger form
            // As far as I can tell, there is no way for that parent form to automatically detect the inputs in a component without JS
            // This is because the vue component is in a shadow dom
            // So for now this just drops the hidden inputs into the the parent form anytime there is a change
            const html = this.identifiersWithValues.map(identifier=>`<input type="hidden" name="author--remote_ids--${identifier.name}" value="${identifier.value}"/>`).join('');
            document.querySelector(this.output_selector).innerHTML = html;
        }
    },
    mounted: function(){
        this.remoteIdsParsed = JSON.parse(this.remote_ids_string);
        this.fetchAllIdentifiers();
    }
}
</script>

<style lang="less">
.wrapper {
  display: grid;
  grid-template-columns: min-content min-content auto;
  grid-row-gap: 1px;
  background-color: #ddd;
}

.box {
  padding: .5rem;
  background-color: #f6f5ee;
}

button {
  margin-left: 1rem;
}

input, select, button {
  padding: 3px;
  font-size: 1.125rem;
}
</style>
