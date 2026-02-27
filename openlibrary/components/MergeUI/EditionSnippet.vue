<template>
  <div class="edition-snippet">
    <img
      loading="lazy"
      :src="cover_url"
      tabindex="0"
      aria-label="Click to enlarge cover image"
      @click="openEnlargedCover"
    >
    <div class="links">
      <a
        :href="edition.key"
        target="_blank"
      >OL</a>
      <a
        v-if="edition.ocaid"
        :href="`https://archive.org/details/${edition.ocaid}`"
        target="_blank"
      >IA</a>
      <a
        v-if="edition.oclc_numbers"
        :href="`https://www.worldcat.org/oclc/${edition.oclc_numbers[0]}?tab=details`"
        target="_blank"
      >WC<span
        v-if="edition.oclc_numbers.length > 1"
        title="This edition has multiple OCLCs"
      >*</span></a>
      <a
        v-if="asins.length"
        :href="`https://www.amazon.com/dp/${asins[0]}`"
        target="_blank"
      >AZ<span
        v-if="asins.length > 1"
        title="This edition has multiple potential ASINs"
      >*</span></a>
    </div>
    <div class="info">
      <b>{{ number_of_pages }} p | {{ languages }} | {{ publish_year }}</b>
      {{ ' ' }}
      <span
        class="publishers"
        :title="`${publishers.join(', ')}`"
      >{{ publishers.join(', ') }}</span>
    </div>
    <hr>
    <div
      class="title"
      :title="full_title"
    >
      {{ full_title }}
    </div>
  </div>
</template>

<script>
import _ from 'lodash';
import ISBN from 'isbn3';

export default {
    props: {
        edition: Object
    },
    computed: {
        publish_year() {
            if (!this.edition.publish_date) return '';
            const m = this.edition.publish_date.match(/\d{4}/);
            return m ? m[0] : null;
        },

        publishers() {
            return this.edition.publishers || [];
        },

        number_of_pages() {
            if (this.edition.number_of_pages) {
                return this.edition.number_of_pages;
            } else if (this.edition.pagination) {
                const m = this.edition.pagination.match(/\d+ ?p/);
                if (m) return parseFloat(m[0]);
            }

            return '?';
        },

        full_title() {
            let title = this.edition.title;
            if (this.edition.subtitle) title += `: ${this.edition.subtitle}`;
            return title;
        },

        cover_id() {
            return this.edition.covers?.[0] ?? null;
        },

        cover_url() {
            if (this.cover_id) return `https://covers.openlibrary.org/b/id/${this.cover_id}-M.jpg`;

            const ocaid = this.edition.ocaid;
            if (ocaid)
                return `https://archive.org/download/${ocaid}/page/cover_w180_h360.jpg`;

            return '';
        },

        languages() {
            if (!this.edition.languages) return '???';
            const langs = this.edition.languages.map(lang => lang.key.split('/')[2]);
            return langs.join(', ');
        },

        asins() {
            return _.uniq([
                ...((this.edition.identifiers && this.edition.identifiers.amazon) || []),
                this.edition.isbn_10 && ISBN.asIsbn10(this.edition.isbn_10),
                this.edition.isbn_13 && ISBN.asIsbn10(this.edition.isbn_13),
            ].filter(x => x));
        }
    },

    methods: {
        openEnlargedCover() {
            let url = '';
            if (this.cover_id) {
                url = `https://covers.openlibrary.org/b/id/${this.cover_id}.jpg`;
            } else if (this.edition.ocaid) {
                const ocaid = this.edition.ocaid;
                url = `https://archive.org/download/${ocaid}/page/cover_w600_h600.jpg`;
            }

            if (!url) return;

            window.open(url, undefined, 'width=600,height=600');
        }
    }
};
</script>

<style>
.edition-snippet {
  border-radius: 4px;
  height: 64px;
  overflow: hidden;
  background: #fff;
  margin-bottom: 4px;
  font-size: 0.95em;
}

.edition-snippet img {
  height: 100%;
  width: 60px;
  background: #eee;
  object-fit: cover;
  object-position: top center;
  float: left;
  margin-right: 7px;
  /* Min Height added for lazy loading so that the lazy loaded images are not 1 pixel and start having many books start loading */
  min-height: 80px;
}
.edition-snippet img:not([src=""]) {
  cursor: zoom-in;
}
.edition-snippet img:hover {
  object-fit: contain;
}

.edition-snippet .links {
  float: right;
  padding-right: 2px;
  padding-top: 4px;
}
.edition-snippet .links a {
  padding: 2px;
}

.edition-snippet .info {
  padding-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edition-snippet .publishers {
  opacity: 0.8;
}

.edition-snippet hr {
  margin: 4px 0;
  color: white;
}
</style>
