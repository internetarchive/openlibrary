<template>
  <table>
    <tr>
      <th>
        <select class="form-control" v-model="selectedIdentifier" name="name">
          <option disabled value="">Select one</option>
          <option v-for="idConfig in identifierConfigsByKey" :key="idConfig.name" :value="idConfig.name">
            {{idConfig.label}}
          </option>
        </select>
      </th>
      <th>
        <input class="form-control" type="text" name="value" id="id-value" v-model="inputValue" @keyup.enter=setIdentifier>
      </th>
      <th>
        <button class="form-control" name="set" :disabled="!setButtonEnabled" @click=setIdentifier>Set</button>
      </th>
    </tr>
    <template v-for="(value, name) in assignedIdentifiers">
      <tr :key="name" v-if="value">
        <td>{{ identifierConfigsByKey[name].label }}</td>
        <td>{{ value }}</td>
        <td>
          <button class="form-control" @click="removeIdentifier(name)">Remove</button>
        </td>
      </tr>
    </template>
  </table>
</template>

<script>
export default {
    // Props are for external options; if a subelement of this is modified,
    // the view automatically re-renders
    props: {
        /** The list of ids currently associated with the entity in the database in string form */
        assigned_ids_string: {
            type: String,
            //default: () =>  "{'wikidata': 'Q10000'}"
        },
        /** everything from https://openlibrary.org/config/author
         * Most importantly:
         * {"identifiers": [{"label": "ISNI", "name": "isni", "notes": "", "url": "http://www.isni.org/@@@", "website": "http://www.isni.org/"}, ... ]}
         */
        author_config_string: {
            type: String
        },
        /** see createHiddenInputs function for usage */
        output_selector: {
            type: String
        }
    },

    // Data is for internal stuff. This needs to be a function so that we get
    // a fresh object every time this is initialized.
    data: () => {
        return {
            selectedIdentifier: '', // Which identifier is selected in dropdown
            inputValue: '', // What user put into input
            assignedIdentifiers: {}, // IDs assigned to the entity Ex: {'viaf': '12632978'}
        }
    },

    computed: {
        identifierConfigsByKey: function(){
            const parsedConfigs = JSON.parse(decodeURIComponent(this.author_config_string))['identifiers'];
            return Object.fromEntries(parsedConfigs.map(e => [e.name, e]));
        },
        setButtonEnabled: function(){
            return this.selectedIdentifier !== '' && this.inputValue !== '';
        }
    },

    methods: {
        setIdentifier: function(){
            // if no identifier selected don't execute
            if (!this.setButtonEnabled) return

            // We use $set otherwise we wouldn't get the reactivity desired
            // See https://vuejs.org/v2/guide/reactivity.html#Change-Detection-Caveats
            this.$set(this.assignedIdentifiers, this.selectedIdentifier, this.inputValue);
            this.inputValue = '';
        },
        /** Removes an identifier with value from memory and it will be deleted from database on save */
        removeIdentifier: function(identifierName){
            this.$set(this.assignedIdentifiers, identifierName, '');
        },
        createHiddenInputs: function(){
            /** Right now, we have a vue component embedded as a small part of a larger form
              * There is no way for that parent form to automatically detect the inputs in a component without JS
              * This is because the vue component is in a shadow dom
              * So for now this just drops the hidden inputs into the the parent form anytime there is a change
              */
            const html = Object.entries(this.assignedIdentifiers)
                .map(([name, value]) => `<input type="hidden" name="author--remote_ids--${name}" value="${value}"/>`)
                .join('');
            document.querySelector(this.output_selector).innerHTML = html;
        }
    },
    created: function(){
        this.assignedIdentifiers = JSON.parse(decodeURIComponent(this.assigned_ids_string));
    },
    watch: {
        assignedIdentifiers:
            {
                handler: function(){this.createHiddenInputs()},
                deep: true
            }
    }
}
</script>

<style lang="less">
// This and .form-control ensure that select, input, and buttons are the same height
select.form-control {
  height: calc(2.25rem + 2px);
}
.form-control {
  padding: .375rem .75rem;
  font-size: 1rem;
  line-height: 1.5;
  border: 1px solid #ced4da;
}
table {
  background-color: #f6f5ee;
  border-collapse: collapse;
}
th {
  text-align: left;
}
td {
  border-top: 1px solid #ddd;
}
th, td {
  padding: .25rem;
}
</style>
