<template>
  <div class="edition-snippet">
    <img :src="cover_url" />
    <div class="links">
      <a :href="edition.key" target="_blank">OL</a>
      <a
        v-if="edition.ocaid"
        :href="`https://archive.org/details/${edition.ocaid}`"
        target="_blank"
      >IA</a>
      <a
        v-if="edition.oclc_numbers"
        :href="`https://www.worldcat.org/oclc/${edition.oclc_numbers[0]}?tab=details`"
        target="_blank"
      >WC<span v-if="edition.oclc_numbers.length > 1" title="This edition has multiple OCLCs">*</span></a>
      <a
        v-if="asins.length"
        :href="`https://www.amazon.com/dp/${asins[0]}`"
        target="_blank"
      >AZ<span v-if="asins.length > 1" title="This edition has multiple potential ASINs">*</span></a>
    </div>
    <div class="info">{{publish_year}} {{publishers.join(', ')}} {{languages}}</div>
    <div class="title" :title="full_title">{{full_title}}</div>
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

        full_title() {
            let title = this.edition.title;
            if (this.edition.subtitle) title += `: ${this.edition.subtitle}`;
            return title;
        },

        cover_url() {
            const id =
        this.edition.covers && this.edition.covers[0]
            ? this.edition.covers[0]
            : null;
            if (id) return `https://covers.openlibrary.org/b/id/${id}-M.jpg`;

            const ocaid = this.edition.ocaid;
            if (ocaid)
                return `https://archive.org/download/${ocaid}/page/cover_w180_h360.jpg`;

            return 'https://covers.openlibrary.org/b/id/-1-M.jpg';
        },

        languages() {
            if (!this.edition.languages) return '';
            const langs = this.edition.languages.map(lang => lang.key.split('/')[2]);
            return `in ${langs.join(', ')}`;
        },

        asins() {
            return _.uniq([
                ...((this.edition.identifiers && this.edition.identifiers.amazon) || []),
                this.edition.isbn_10 && ISBN.asIsbn10(this.edition.isbn_10),
                this.edition.isbn_13 && ISBN.asIsbn10(this.edition.isbn_13),
            ].filter(x => x));
        }
    }
};
</script>

<style lang="less">
.edition-snippet {
  border: 1px solid;
  border-radius: 4px;
  height: 60px;
  overflow: hidden;
  width: calc(100% - 20px);

  .info {
    font-weight: bold;
  }

  img {
    height: 60px;
    width: 60px;
    background: #ddd;
    border-right: 2px solid #ddd;
    object-fit: cover;
    object-position: top center;
    float: left;
    margin-right: 5px;
    &:hover {
      object-fit: contain;
    }
  }

  .links {
    float: right;
    padding-right: 2px;
    a {
      padding: 2px;
    }
  }
}
</style>
