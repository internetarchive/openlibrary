<template>
  <a class="lazy-book-card" :href="link" :class="{ 'loading' : loading, 'errored' : errored}">
    <div class="cover">
      <img :src="coverSrc">
    </div>
    <div class="info">
      <div class="title">{{ title }}</div>
      <div class="byline">{{ byline }}</div>
      <div class="identifier">{{ identifier }}</div>
    </div>
  </a>
</template>

<script>
import CONFIGS from '../../configs';
import Promise from 'promise-polyfill';
export default {
    props: {
        isbn: {
            type: String,
        },
        tentativeCover: {
            type: String,
            default: null,
        },
    },
    data() {
        return {
            link: null,
            coverSrc: this.tentativeCover,
            title: this.isbn,
            byline: null,
            identifier: null,
            errored: false,
            loading: true,
        }
    },
    methods: {
        async fromISBN(isbn) {
            fetch(`https://${CONFIGS.OL_BASE_PUBLIC}/isbn/${isbn}.json`).then(r => r.json())
                .then(editionRecord => {
                    this.title = editionRecord.title;
                    this.identifier = isbn;
                    this.link = editionRecord.key;

                    if (editionRecord.covers) {
                        const coverId = editionRecord.covers.find(x => x !== -1);
                        if (coverId) {
                            this.coverSrc = `https://covers.openlibrary.org/b/id/${coverId}-M.jpg`;
                        }
                    }
                    return fetch(`https://${CONFIGS.OL_BASE_PUBLIC}${editionRecord.works[0].key}.json`).then(r => r.json())
                }).then(workRecord => {
                    return Promise.all(
                        workRecord.authors
                            .map(a => fetch(`https://${CONFIGS.OL_BASE_PUBLIC}${a.author.key}.json`).then(r => r.json()))
                    );
                }).then(authorRecords => {
                    this.loading = false;
                    this.byline = authorRecords.map(a => a.name).join(', ');
                })
                // eslint-disable-next-line no-unused-vars
                .catch((err) => {
                    this.loading = false;
                    this.errored = true;
                });
        },
    },
    mounted() {
        this.fromISBN(this.isbn);
    },
}
</script>

<style lang="less">
  @keyframes pulse {
    0% { opacity: 0; }
    100% { opacity: .95; }
  }

  a.lazy-book-card {
    background: hsl(0, 0%, 100%);
    flex-shrink: 0;
    margin-right: 6px;
    width: 80vw;
    max-width: 300px;
    height: 120px;
    border: 1px solid hsl(0, 0%, 67%);
    border-radius: 4px;
    display: flex;
    overflow: hidden;
    color: hsl(0, 0%, 0%);
    text-decoration: none;
    position: relative;
    transition-property: background-color border-color;
    transition-duration: .2s;

    &:first-child { animation: slideUp .8s; }
    &:nth-child(2) { animation: shiftRight .8s; }
    &:hover {
      background: lighten(hsl(240, 100%, 50%), 45%);
      border-color: lighten(hsl(240, 100%, 50%), 15%);
      color: lighten(hsl(240, 100%, 50%), 10%);
    }
    &::before {
      display: none;
      content: "";
      position: absolute;
      width: 6px;
      height: 6px;
      border-radius: 100px;
      margin: 10px;
      right: 0;
    }
    &.loading::before {
      display: block;
      background: hsl(240, 100%, 50%);
      opacity: 0;
      animation: pulse .5s infinite alternate;
      // Only show loading animation if it takes
      // longer than this
      animation-delay: .5s;
    }
    &.errored::before {
      display: block;
      background: hsl(8, 78%, 49%);
    }
    .title { font-weight: bold; line-height: 1.1em; }
    .byline { font-size: .9em; margin-top: .1em; }
    .cover {
      width: 25%;
      img { width: 100%; height: 100%; object-fit: cover; }
    }
    .identifier {
      margin-top: 4px;
      padding-top: 4px;
      color: hsl(0, 0%, 33%);
      border-top: 1px dotted;
      font-family: monospace;
      font-size: 1.2em;
    }
    .info {
      flex: 1;
      padding: 8px;
    }
  }
</style>
