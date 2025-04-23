<template>
  <div class="world-map">
    <prime-select
      v-model="selected"
      :options="countries"
      option-label="name"
      placeholder="Select a country"
    />
    <WorldMapRaw @click="handleMapClick" />
  </div>
</template>

<script>
import WorldMapRaw from './WorldMapRaw.vue';
import Select from 'primevue/select';

export default {
    name: 'WorldMap',
    components: {
        'prime-select': Select,
        WorldMapRaw,
    },
    emits: ['country-selected'],
    data() {
        return {
            selected: null,
            countries: [],
        }
    },
    watch: {
        selected(newVal) {
            if (newVal) {
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
        this.countries = countryEls
            .map(el => ({
                name: el.querySelector('title').textContent.trim(),
                id: el.id,
            }));
    },
    methods: {
        handleMapClick(event) {
            const countryEl = event.target.closest('svg > .landxx[id]');
            if (!countryEl) return;
            this.selected = this.countries.find(country => country.id === countryEl.id);
        },
    }

};
</script>

<style>
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
</style>
