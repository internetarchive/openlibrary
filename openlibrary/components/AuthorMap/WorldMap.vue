<template>
  <div class="world-map">
    <prime-autocomplete
      v-model="selected"
      class="country-autocomplete"
      :suggestions="filteredCountries"
      option-label="name"
      placeholder="Select a country"
      dropdown
      :force-selection="true"
      @complete="searchCountry"
    >
      <template #option="{ option }">
        <div class="flex items-center">
          {{ option.emoji }}
          <span>{{ option.name }}</span>
        </div>
      </template>
    </prime-autocomplete>
    <WorldMapRaw @click="handleMapClick" />
  </div>
</template>

<script>
import WorldMapRaw from './WorldMapRaw.vue';
import AutoComplete from 'primevue/autocomplete';

export default {
    name: 'WorldMap',
    components: {
        'prime-autocomplete': AutoComplete,
        WorldMapRaw,
    },
    emits: ['country-selected'],
    data() {
        return {
            // countryQuery: '',
            /** @type {{ name: string, id: string } | undefined} */
            selected: null,
            /** @type {Array<{ name: string, id: string }>} */
            countries: [],
            /** @type {Array<{ name: string, id: string }>} */
            filteredCountries: [],
        }
    },
    watch: {
        selected(newVal) {
            if (newVal?.id) {
                this.$emit('country-selected', newVal);
                // find the country element in the map and add a selected class
                const svg = this.$el.querySelector('svg.world-map-raw');
                const oldSelected = svg.querySelector('svg.world-map-raw > .selected');
                if (oldSelected) {
                    oldSelected.classList.remove('selected');
                }
                const newSelected = svg.querySelector(`svg.world-map-raw > .landxx#${newVal.id}`);
                if (newSelected) {
                    newSelected.classList.add('selected');
                }
            }
        },
    },
    mounted() {
        // fetch the `<title>` attributes and display them as countries
        // in the select dropdown
        window.EL = this;
        const countryEls = Array.from(this.$el.querySelectorAll('svg.world-map-raw > .landxx[id]'));
        const countries = countryEls
            .map(el => ({
                name: el.querySelector('title').textContent.trim(),
                id: el.id,
                emoji: el.id
                    .toUpperCase()
                    .replace(/./g, char =>
                        String.fromCodePoint(char.charCodeAt(0) + 127397)
                    )
            }));
        countries.sort((a, b) => a.name.localeCompare(b.name));
        this.countries = countries;
    },
    methods: {
        handleMapClick(event) {
            const countryEl = event.target.closest('svg > .landxx[id]');
            if (!countryEl) return;
            this.selected = this.countries.find(country => country.id === countryEl.id);
        },
        searchCountry(event) {
            const query = event.query.toLowerCase();
            this.filteredCountries = this.countries.filter(country =>
                country.name.toLowerCase().includes(query)
            );
        },
    }
};
</script>

<style>
.world-map {
    position: relative;
}
.country-autocomplete {
    position: absolute !important;
    z-index: 1;
    bottom: 0;
    left: 0;
    margin: 10px;
}
svg {
  width: 100%;
}
svg > .landxx {
  cursor: pointer;
  transition: fill 0.3s;
}
svg > .landxx:hover, svg > .landxx:hover * {
  fill: #f00;
}

svg > .landxx.selected, svg > .landxx.selected * {
  fill: #f00;
}
/** TMP: Needed because of the janky import of all OL styles. */
input[type="email"], input[type="text"] {
    margin: unset !important;
}
</style>
