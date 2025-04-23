<template>
  <div class="author-map">
    <WorldMap @country-selected="handleCountrySelected" />

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
        async handleCountrySelected(country) {
            if (this.state === 'loading') return;
            this.selectedCountry = country;
            this.state = 'loading';
            this.authors = await getAuthorsForCountry(country.id.toUpperCase());
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
</style>
