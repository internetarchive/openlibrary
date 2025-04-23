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
                const newSelected = svg.querySelector(`svg.world-map-raw > *:not(.oceanxx)#${newVal.id}`);
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
        const titleEls = Array.from(this.$el.querySelectorAll('svg.world-map-raw > [id] > title, svg.world-map-raw > g > [id] > title'));
        const countryEls = titleEls.map(el => this.findCountryElement(el));
        countryEls.forEach(el => {
            el.classList.add('selectable');
        });
        const countries = countryEls
            .map(el => ({
                name: el.querySelector('title').textContent.trim(),
                id: el.id,
                el,
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
        findCountryElement(el) {
            let curEl = el;
            while (curEl?.id?.length !== 2) {
                if (curEl.tagName === 'svg') {
                    return null;
                }
                curEl = curEl.parentElement;
            }
            return curEl;
        },
        handleMapClick(event) {
            const countryEl = this.findCountryElement(event.target);
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
svg > .selectable {
  cursor: pointer;
  transition: fill 0.3s;
}
svg > .selectable:hover, svg > .selectable:hover * {
  fill: #f00;
}

svg > .selectable.selected, svg > .selectable.selected * {
  fill: #f00;
}
/** TMP: Needed because of the janky import of all OL styles. */
input[type="email"], input[type="text"] {
    margin: unset !important;
}
</style>
