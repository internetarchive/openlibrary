<template>
  <div class="field-container" :class="`field-${field}`" :title="title">
    <!-- Type -->
    <div v-if="field == 'type'" :title="JSON.stringify(value)">{{value.key}}</div>
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

    <!-- Description/First Sentence -->
    <TextDiff
      v-else-if="['description','first_sentence'].includes(field)"
      resolution="word"
      :title="JSON.stringify(value)"
      :left="value.value || value"
      :right="merged ? ((field in merged && merged[field].value) || merged[field] || '') : (value.value || value)"
    />

    <!-- Defaults -->
    <TextDiff
      v-else-if="typeof(value) == 'string'"
      :left="value"
      :right="merged ? (merged[field] || '') : value"
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
