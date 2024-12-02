<template>
  <div class="field-container" :class="`field-${field}`" :title="title">
    <!-- Type -->
    <div v-if="field == 'type'" :title="JSON.stringify(value)">{{value.key}}</div>
    <!-- Location -->
    <div v-else-if="field == 'location'" :title="JSON.stringify(value)">{{value}}</div>
    <!-- Authors Array -->
    <AuthorRoleTable v-else-if="field == 'authors'" :roles="value" />
    <!-- Excerpts Array -->
    <ExcerptsTable v-else-if="field == 'excerpts'" :excerpts="value" />
    <!-- Key -->
    <a
      v-else-if="field == 'key'" :href="value" target="_blank"
    >{{value.slice("/works/".length)}}</a>
    <div v-else-if="field == 'covers'" class="wrapper">
      <a
        class="cover"
        v-for="id in value"
        :key="id"
        :href="`https://covers.openlibrary.org/b/id/${id}.jpg`"
        target="_blank"
      >
        <img
          loading="lazy"
          :src="`https://covers.openlibrary.org/b/id/${id}-M.jpg`"
          :srcset="`https://covers.openlibrary.org/b/id/${id}-M.jpg, https://covers.openlibrary.org/b/id/${id}-L.jpg 1.5x, https://covers.openlibrary.org/b/id/${id}.jpg 2x`"
        />
      </a>
    </div>

    <!-- Date Fields -->
    <time
      v-else-if="['created', 'last_modified'].includes(field)"
      :datetime="value.value"
      :title="value.value"
    >{{value.value.split("T")[0]}}</time>

    <!-- Subjects -->
    <ul
      v-else-if="['subjects','subject_places','subject_people','subject_times'].includes(field)"
      class="reset pill-list"
    >
      <li class="pill" v-for="string in value" :key="string">{{string}}</li>
    </ul>

    <!-- Links -->
    <ul
      v-else-if="['links'].includes(field)"
      class="reset links"
    >
      <li class="link" v-for="link in value" :key="link"><a :href="`${link.url}`" target="_blank">{{link.title}}</a></li>
    </ul>

    <!-- Other Array fields -->
      <ul
      v-else-if="['dewey_number','lc_classifications'].includes(field)"
      class="reset list"
    >
      <li v-for="string in value" :key="string">{{string}}</li>
    </ul>
    <!-- Description/First Sentence -->
    <TextDiff
      v-else-if="['description','first_sentence'].includes(field)"
      resolution="word"
      :title="JSON.stringify(value)"
      :left="value.value || value"
      :right="merged ? ((field in merged && merged[field].value) || merged[field] || '') : (value.value || value)"
      :show_diffs="show_diffs"
    />

    <!-- Defaults -->
    <TextDiff
      v-else-if="typeof(value) == 'string'"
      :left="value"
      :right="merged ? (merged[field] || '') : value"
      :show_diffs="show_diffs"
    />
    <div v-else-if="typeof(value) == 'number'">{{value}}</div>
    <div v-else>
      <pre>{{JSON.stringify(value)}}</pre>
    </div>
  </div>
</template>

<script>
import AuthorRoleTable from './AuthorRoleTable.vue';
import ExcerptsTable from './ExcerptsTable.vue';
import TextDiff from './TextDiff.vue';

export default {
    components: {
        AuthorRoleTable,
        ExcerptsTable,
        TextDiff
    },
    props: {
        field: {
            type: String,
            required: true
        },
        value: {
            required: true
        },
        merged: {
            type: Object,
            required: false
        },
        show_diffs: {
            type: Boolean
        }
    },
    computed: {
        title() {
            let title = `.${this.field}`;
            if (this.value instanceof Array) {
                const length = this.value.length;
                title += ` (${length} item${length === 1 ? '' : 's'})`;
            }
            return title;
        }
    }
};
</script>

<style scoped>
.cover img {
  min-height: 80px; /* Min Height added for lazy loading so that the lazy loaded images are not 1 pixel and start having many books start loading */
  height: auto; /* Maintain aspect ratio */
  object-fit: cover; /* Prevent distortion */
}
</style>
