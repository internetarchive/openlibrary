<template>
  <div
    class="identifiers wrapper"
    role="table"
  >
    <div
      id="identifiers-form"
      class="identifiers-table"
      role="row"
    >
      <select
        v-model="selectedIdentifier"
        class="form-control cell1"
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

      <div
        class="cell2"
        role="cell"
      >
        <input
          id="id-value"
          v-model.trim="inputValue"
          class="form-control"
          type="text"
          name="value"
          @keyup.enter="setIdentifier"
        >
      </div>

      <div
        class="cell3"
        role="cell"
      >
        <button
          class="form-control"
          name="set"
          :disabled="!setButtonEnabled"
          @click="setIdentifier"
        >
          Set
        </button>
      </div>
    </div>

    <template v-for="(value, name) in assignedIdentifiers">
      <div
        v-for="(item, idx) in (saveIdentifiersAsList ? value : [value])"
        :key="name + idx"
        class="assigned-identifiers-table"
        role="row"
      >
        <div
          class="identifier-name"
          role="rowheader"
        >
          {{ identifierConfigsByKey[name]?.label ?? name }}
        </div>

        <div
          class="identifier-value"
          role="cell"
        >
          {{ item }}
        </div>

        <div
          class="remove-button"
          role="cell"
        >
          <!-- 🔗 Preview Button -->
          <button
            type="button"
            class="form-control"
            aria-label="Preview identifier"
            title="Preview identifier link"
            @click="previewIdentifier(name, item)"
          >
            🔗
          </button>

          <!-- Remove Button -->
          <button
            type="button"
            class="form-control"
            :disabled="!isAdmin && name === 'ocaid'"
            :title="!isAdmin && name === 'ocaid' ? 'Only librarians can edit this identifier' : ''"
            @click="removeIdentifier(name, idx)"
          >
            Remove
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import { errorDisplay, validateIdentifiers } from './IdentifiersInput/utils/utils.js';

const identifierPatterns = {
    wikidata: /^Q[1-9]\d*$/i,
    isni: /^[0]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{3}[0-9X]$/i,
    lc_naf: /^n[bors]?[0-9]+$/,
    amazon: /^B[0-9A-Za-z]{9}$/,
    youtube: /^@[A-Za-z0-9_\-.]{3,30}/,
};

export default {
    props: {
        assigned_ids_string: { type: String },
        id_config_string: { type: String, required: true },
        output_selector: { type: String, required: true },
        input_prefix: { type: String },
        multiple: { type: String, default: 'false' },
        admin: { type: String, default: 'false' },
        popular_ids: { type: String, default: '' },
    },

    data: () => ({
        selectedIdentifier: '',
        inputValue: '',
        assignedIdentifiers: {}
    }),

    computed: {
        idConfigs() {
            return JSON.parse(decodeURIComponent(this.id_config_string));
        },
        popularIds() {
            if (this.popular_ids) {
                const popularIdNames = JSON.parse(decodeURIComponent(this.popular_ids));
                return this.idConfigs.filter(config => popularIdNames.includes(config.name));
            }
            return [];
        },
        identifierConfigsByKey() {
            return Object.fromEntries(this.idConfigs.map(e => [e.name, e]));
        },
        saveIdentifiersAsList() {
            return this.multiple.toLowerCase() === 'true';
        },
        setButtonEnabled() {
            return this.selectedIdentifier !== '' && this.inputValue !== '' && (this.isAdmin || this.selectedIdentifier !== 'ocaid');
        },
        hasPopularIds() {
            return Object.keys(this.popularIds).length !== 0;
        },
        isAdmin() {
            return this.admin.toLowerCase() === 'true';
        }
    },

    watch: {
        assignedIdentifiers: {
            handler() { this.createHiddenInputs(); },
            deep: true
        },
        inputValue: {
            handler() { this.selectIdentifierByInputValue(); }
        }
    },

    created() {
        this.assignedIdentifiers = JSON.parse(decodeURIComponent(this.assigned_ids_string));

        if (this.assignedIdentifiers.length === 0) {
            this.assignedIdentifiers = {};
            return;
        }

        if (this.saveIdentifiersAsList) {
            const edition_identifiers = {};
            this.assignedIdentifiers.forEach(entry => {
                if (!edition_identifiers[entry.name]) {
                    edition_identifiers[entry.name] = [entry.value];
                } else {
                    edition_identifiers[entry.name].push(entry.value);
                }
            });
            this.assignedIdentifiers = edition_identifiers;
        }
    },

    methods: {
        setIdentifier() {
            if (!this.setButtonEnabled) return;

            if (this.selectedIdentifier === 'isni') {
                this.inputValue = this.inputValue.replace(/\s/g, '');
            }

            if (this.saveIdentifiersAsList) {
                const existingIds = this.assignedIdentifiers[this.selectedIdentifier] ?? [];

                if (this.selectedIdentifier === 'ocaid' && existingIds.length > 0) {
                    errorDisplay('Only one Internet Archive ID is allowed per edition.', this.output_selector);
                    return;
                }

                const validEditionId = validateIdentifiers(
                    this.selectedIdentifier,
                    this.inputValue,
                    existingIds,
                    this.output_selector
                );

                if (validEditionId) {
                    if (!this.assignedIdentifiers[this.selectedIdentifier]) {
                        this.inputValue = [this.inputValue];
                    } else {
                        const updateIdentifiers = this.assignedIdentifiers[this.selectedIdentifier];
                        updateIdentifiers.push(this.inputValue);
                        this.inputValue = updateIdentifiers;
                    }
                } else return;

            } else if (this.assignedIdentifiers[this.selectedIdentifier]) {
                errorDisplay(
                    `An identifier for ${this.identifierConfigsByKey[this.selectedIdentifier].label} already exists.`,
                    this.output_selector
                );
                return;
            } else {
                errorDisplay('', this.output_selector);
            }

            this.assignedIdentifiers[this.selectedIdentifier] = this.inputValue;
            this.inputValue = '';
            this.selectedIdentifier = '';
        },

        removeIdentifier(identifierName, idx = 0) {
            if (this.saveIdentifiersAsList) {
                this.assignedIdentifiers[identifierName].splice(idx, 1);
            } else {
                this.assignedIdentifiers[identifierName] = '';
            }
        },

        previewIdentifier(name, value) {
            if (!value) return;

            const url = this.resolveIdentifierUrl(name, value);
            if (url) {
                window.open(url, '_blank', 'noopener,noreferrer');
            }
        },

        resolveIdentifierUrl(name, value) {
            const config = this.identifierConfigsByKey[name];

            if (config && config.url) {
                return config.url.replace('@@@', value);
            }

            if (name === 'wikidata') {
                return `https://www.wikidata.org/wiki/${value}`;
            }

            if (name === 'isbn_10' || name === 'isbn_13') {
                return `https://openlibrary.org/isbn/${value}`;
            }

            return null;
        },

        createHiddenInputs() {
            let html = '';

            if (this.saveIdentifiersAsList) {
                let num = 0;
                for (const [key, value] of Object.entries(this.assignedIdentifiers)) {
                    for (const idx in value) {
                        html += `<input type="hidden" name="${this.input_prefix}--${num}--name" value="${key}"/>`;
                        html += `<input type="hidden" name="${this.input_prefix}--${num}--value" value="${value[idx]}"/>`;
                        num += 1;
                    }
                }
            } else {
                html = Object.entries(this.assignedIdentifiers)
                    .map(([name, value]) =>
                        `<input type="hidden" name="${this.input_prefix}--${name}" value="${value}"/>`
                    ).join('');
            }

            document.querySelector(this.output_selector).innerHTML = html;
        },

        selectIdentifierByInputValue() {
            if (this.saveIdentifiersAsList) return;

            for (const idtype in identifierPatterns) {
                if (this.inputValue.match(identifierPatterns[idtype])) {
                    this.selectedIdentifier = idtype;
                    break;
                }
            }
        }
    }
}
</script>
