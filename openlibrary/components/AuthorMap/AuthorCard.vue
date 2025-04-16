<template>
  <li class="searchResultItem">
    <img
      :src="getCoverUrl(author.key)"
      itemprop="image"
      class="cover author"
      :alt="`Photo of ${author.name}`"
    >
    <div class="details">
      <a
        :href="`https://openlibrary.org/authors/${author.key}`"
        class="larger"
      >{{ author.name }}</a>&nbsp;<span class="brown small">{{ author.date }}</span>
      <br>
      <span class="small grey">
        <b>{{ author.work_count }} books</b>
        <template v-if="author.top_subjects">
          about {{ author.top_subjects.join(', ') }},
        </template>
        including <i>{{ author.top_work || '' }}</i>
      </span>
    </div>
  </li>
</template>

<script>
import CONFIGS from '../configs.js';
export default {
    name: 'AuthorCard',
    props: {
        author: {
            type: Object,
            required: true,
        },
    },
    methods: {
        getCoverUrl(key) {
            const olid = key.split('/').pop();
            return `${CONFIGS.OL_BASE_COVERS}/a/olid/${olid}-M.jpg`;
        },
    },
};
</script>
