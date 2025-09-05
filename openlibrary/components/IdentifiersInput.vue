<template>
  <table class="identifiers">
    <tr id="identifiers-form">
      <th>
        <select
          v-model="selectedIdentifier"
          class="form-control"
          name="name"
        >
          <option
            disabled
            value=""
          >
            Select one
          </option>
          <template v-if="hasPopularIds">
            <option
              v-for="entry in popularIds.filter(e => isAdmin || e.name !== 'ocaid')"
              :key="entry.name"
              :value="entry.name"
            >
              {{ entry.label }}
            </option>
            <option
              disabled
              value=""
            >
              ---
            </option>
          </template>
          <option
            v-for="idConfig in identifierConfigsByKey"
            :key="idConfig.name"
            :value="idConfig.name"
            :disabled="!isAdmin && idConfig.name === 'ocaid'"
            :title="!isAdmin && idConfig.name === 'ocaid' ? 'Only librarians can edit this identifier' : ''"
          >
            {{ idConfig.label }}
          </option>
        </select>
      </th>
      <th>
        <input
          id="id-value"
          v-model.trim="inputValue"
          class="form-control"
          type="text"
          name="value"
          @keyup.enter="setIdentifier"
        >
      </th>
      <th>
        <button
          class="form-control"
          name="set"
          :disabled="!setButtonEnabled"
          @click="setIdentifier"
        >
          Set
        </button>
      </th>
    </tr>
    <template v-for="(value, name) in assignedIdentifiers">
      <tr
        v-if="value && !saveIdentifiersAsList"
        :key="name"
      >
        <td>{{ identifierConfigsByKey[name]?.label ?? name }}</td>
        <td>{{ value }}</td>
        <td>
          <button
            class="form-control"
            @click="removeIdentifier(name)"
          >
            Remove
          </button>
        </td>
      </tr>
      <template v-else-if="value && saveIdentifiersAsList">
        <tr
          v-for="(item, idx) in value"
          :key="name + idx"
        >
          <td>{{ identifierConfigsByKey[name]?.label ?? name }}</td>
          <td>{{ item }}</td>
          <td>
            <button
              class="form-control"
              :disabled="!isAdmin && name === 'ocaid'"
              :title="!isAdmin && name === 'ocaid' ? 'Only librarians can edit this identifier' : ''"
            >
              Remove
            </button>
          </td>
        </tr>
      </template>
    </template>
  </table>
</template>

<script>
import { errorDisplay, validateIdentifiers } from './IdentifiersInput/utils/utils.js';
const identifierPatterns  = {
    wikidata: /^Q[1-9]\d*$/i,
    isni: /^[0]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{3}[0-9X]$/i,
    lc_naf: /^n[bors]?[0-9]+$/,
    amazon: /^B[0-9A-Za-z]{9}$/,
    youtube: /^@[A-Za-z0-9_\-.]{3,30}/,
}

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
        id_config_string: {
            type: String,
            required: true
        },
        /** see createHiddenInputs function for usage
         * #hiddenEditionIdentifiers, #hiddenWorkIdentifiers
         */
        output_selector: {
            type: String,
            required: true
        },
        /*
        Where to save; eg author--remote_ids-- for authors or
        edition--identifiers-- for editions
        */
        input_prefix: {
            type: String
        },
        /** Editions and works can have multiple identifiers in the form of a list
         * Not applicable to author identifiers
         */
        multiple: {
            type: String,
            default: 'false',
        },
        admin: {
            type: String,
            default: 'false',
        },
        /** Maintains identifier order in the dropdown list
         * Expects a list containing the name field from the
         * respective identifiers.yaml file
        */
        popular_ids: {
            type: String,
            default: '',
        },
    },

    // Data is for internal stuff. This needs to be a function so that we get
    // a fresh object every time this is initialized.
    data: () => {
        return {
            selectedIdentifier: '', // Which identifier is selected in dropdown
            inputValue: '', // What user put into input
            assignedIdentifiers: {}, // IDs assigned to the entity Ex: {'viaf': '12632978'} or {'abaa': ['123456','789012']}
            isAdmin: false,
        }
    },

    computed: {
        idConfigs: function() {
            return JSON.parse(decodeURIComponent(this.id_config_string))
        },
        popularIds: function() {
            if (this.popular_ids) {
                const popularIdNames = JSON.parse(decodeURIComponent(this.popular_ids));
                return this.idConfigs.filter((config) => popularIdNames.includes(config.name));
            }
            return [];
        },
        identifierConfigsByKey: function() {
            return Object.fromEntries(this.idConfigs.map(e => [e.name, e]));
        },
        saveIdentifiersAsList: function() {
            return this.multiple.toLowerCase() === 'true';
        },
        setButtonEnabled: function(){
            return this.selectedIdentifier !== '' && this.inputValue !== '' && (this.isAdmin || this.selectedIdentifier !== 'ocaid');
        },
        hasPopularIds: function() {
            return Object.keys(this.popularIds).length !== 0;
        }
    },
    watch: {
        assignedIdentifiers:
            {
                handler: function(){this.createHiddenInputs()},
                deep: true
            },
        inputValue:
            {
                handler: function(){this.selectIdentifierByInputValue()},
            },
    },
    created: function(){
        this.isAdmin = this.admin.toLowerCase() === 'true';
        this.assignedIdentifiers = JSON.parse(decodeURIComponent(this.assigned_ids_string));
        if (this.assignedIdentifiers.length === 0) {
            this.assignedIdentifiers = {}
            return;
        }
        if (this.saveIdentifiersAsList) {
            const edition_identifiers = {};
            this.assignedIdentifiers.forEach(entry => {
                if (!edition_identifiers[entry.name]) {
                    edition_identifiers[entry.name] = [entry.value];
                } else {
                    edition_identifiers[entry.name].push(entry.value)
                }
            })
            this.assignedIdentifiers = edition_identifiers;
        }
    },

    methods: {
        setIdentifier: function(){
            // if no identifier selected don't execute
            if (!this.setButtonEnabled) return

            if (this.selectedIdentifier === 'isni') {
                this.inputValue = this.inputValue.replace(/\s/g, '')
            }
            if (this.saveIdentifiersAsList) {
                // collect id values of matching type, or empty array if none present
                const existingIds = this.assignedIdentifiers[this.selectedIdentifier] ?? [];
                const validEditionId = validateIdentifiers(this.selectedIdentifier, this.inputValue, existingIds, this.output_selector);
                if (validEditionId) {
                    if (!this.assignedIdentifiers[this.selectedIdentifier]) {
                        this.inputValue = [this.inputValue];
                    } else {
                        const updateIdentifiers = this.assignedIdentifiers[this.selectedIdentifier]
                        updateIdentifiers.push(this.inputValue);
                        this.inputValue = updateIdentifiers;
                    }
                } else {
                    return;
                }
            } else if (this.assignedIdentifiers[this.selectedIdentifier]) {
                errorDisplay(`An identifier for ${this.identifierConfigsByKey[this.selectedIdentifier].label} already exists.`, this.output_selector)
                return;
            } else { errorDisplay('', this.output_selector) }

            this.assignedIdentifiers[this.selectedIdentifier] = this.inputValue;
            this.inputValue = '';
            this.selectedIdentifier = '';
        },
        /** Removes an identifier with value from memory and it will be deleted from database on save */
        removeIdentifier: function(identifierName, idx = 0) {
            if (this.saveIdentifiersAsList) {
                this.assignedIdentifiers[identifierName].splice(idx, 1);
            } else {
                this.assignedIdentifiers[identifierName] = '';
            }
        },
        createHiddenInputs: function(){
            /** Right now, we have a vue component embedded as a small part of a larger form
              * There is no way for that parent form to automatically detect the inputs in a component without JS
              * This is because the vue component is in a shadow dom
              * So for now this just drops the hidden inputs into the the parent form anytime there is a change
              */
            let html = '';
            // should save a list of ids for work + edition identifiers
            if (this.saveIdentifiersAsList) {
                let num = 0;
                for (const [key, value] of Object.entries(this.assignedIdentifiers)) {
                    for (const idx in value) {
                        html += `<input type="hidden" name="${this.input_prefix}--${num}--name" value="${key}"/>`
                        html += `<input type="hidden" name="${this.input_prefix}--${num}--value" value="${value[idx]}"/>`
                        num += 1;
                    }
                }
            }
            else {
                html = Object.entries(this.assignedIdentifiers)
                    .map(([name, value]) => `<input type="hidden" name="${this.input_prefix}--${name}" value="${value}"/>`).join('');
            }
            document.querySelector(this.output_selector).innerHTML = html;
        },
        selectIdentifierByInputValue: function() {
            // Ignore for edition identifiers
            if (this.saveIdentifiersAsList) {
                return;
            }
            // Selects the dropdown identifier based on the input value when possible
            for (const idtype in identifierPatterns) {
                if (this.inputValue.match(identifierPatterns[idtype])){
                    this.selectedIdentifier = idtype;
                    break;
                }
            }

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
