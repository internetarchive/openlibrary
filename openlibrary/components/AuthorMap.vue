<template>
  <div class="author-map">
    <WorldMap @click="handleMapClick" />

    <h2 v-if="selectedCountry">
      Authors from {{ selectedCountry.name }}
    </h2>
    <div
      v-if="state === 'loading'"
      class="loading"
    >
      <p>Loading...</p>
    </div>
    <ul v-if="state === 'idle' && authors.length">
      <AuthorCard
        v-for="author in authors"
        :key="author.key"
        :author="author"
      />
    </ul>
  </div>
</template>

<script>
import AuthorCard from './AuthorMap/AuthorCard.vue';
import WorldMap from './AuthorMap/WorldMap.vue'
import { getAuthorsForCountry } from './AuthorMap/utils.js';
export default {
    name: 'AuthorMap',
    components: {
        WorldMap,
        AuthorCard,
    },
    data() {
        return {
            /** @type {'idle' | 'loading'} */
            state: 'idle',
            authors: [],
            selectedCountry: null,
        }
    },
    methods: {
        async handleMapClick(event) {
            if (this.state === 'loading') return;
            let countryEl = event.target.closest('.landxx');
            // keep going up to parent most landxx
            while (countryEl.parentElement.closest('.landxx')) {
                countryEl = countryEl.parentElement.closest('.landxx');
            }
            if (!countryEl) return;
            this.selectedCountry = {
                id: countryEl.id,
                name: countryEl.querySelector('title').textContent,
            };
            this.state = 'loading';
            this.authors = await getAuthorsForCountry(countryEl.id.toUpperCase());
            this.state = 'idle';
        }
    }
}
</script>

<style>
@import url('https://openlibrary.org/static/build/page-user.css?v=2a5a81c9aaeafbf52b95aa1f8dbae42f');
.author-map {
  max-width: 900px;
  margin: 0 auto;
}
svg {
  width: 100%;
}
.landxx {
  cursor: pointer;
  transition: fill 0.3s;
}
svg > .landxx:hover, svg > .landxx:hover * {
  fill: #f00;
}
</style>
