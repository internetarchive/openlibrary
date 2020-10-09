<template>
  <div id="app">
    <BookRoom
      :classification="settingsState.selectedClassification"
      :filter="computedFilter"
      :class="bookRoomClass"
      :features="bookRoomFeatures"
    />

    <LibraryToolbar :filterState="filterState" :settingsState="settingsState" />
  </div>
</template>

<script>
import BookRoom from './LibraryExplorer/components/BookRoom';
import LibraryToolbar from './LibraryExplorer/components/LibraryToolbar';
import DDC from './LibraryExplorer/ddc.json';
import LCC from './LibraryExplorer/lcc.json';
import { recurForEach } from './LibraryExplorer/utils.js';

export default {
    components: {
        BookRoom,
        LibraryToolbar,
    },
    data() {
        const classifications = [
            {
                name: 'DDC',
                field: 'ddc',
                fieldTransform: ddc => ddc,
                root: recurForEach({ children: DDC }, n => {
                    n.position = n.offset = 0;
                    n.requests = {};
                })
            },
            {
                name: 'LCC',
                field: 'lcc',
                fieldTransform: lcc =>
                    lcc
                        .replace(/-+0+/, '')
                        .replace(/\.0+\./, '.')
                        .replace(/\.0+$/, ' ')
                        .replace(/-+/, '')
                        .replace(/0+(\.\D)/, ($0, $1) => $1),
                root: recurForEach({ children: LCC }, n => {
                    n.position = n.offset = 0;
                    n.requests = {};
                })
            }
        ];
        return {
            filterState: {
                filter: '',
                /** @type { '' | 'true' | 'false' } */
                has_ebook: '',
                language: '',
                age: '',
                year: '[1985 TO 9998]'
            },

            settingsState: {
                selectedClassification: classifications[0],
                classifications,

                styles: {
                    book: {
                        options: [
                            'default',
                            '3d',
                            'spines',
                            '3d-spines',
                            '3d-flat'
                        ],
                        selected: 'default'
                    },

                    shelf: {
                        options: ['default', 'visual'],
                        selected: 'default'
                    },

                    shelfLabel: {
                        options: ['slider', 'expander'],
                        selected: 'slider'
                    },

                    aesthetic: {
                        options: ['mockup', 'wip'],
                        selected: 'wip'
                    },
                }
            },
        };
    },

    computed: {
        computedFilter() {
            const filters = this.filterState.filter ? [this.filterState.filter] : [];
            if (this.filterState.has_ebook) {
                filters.push(`has_fulltext:${this.filterState.has_ebook}`);
            }

            if (this.filterState.language) {
                filters.push(`language:${this.filterState.language}`);
            }
            if (this.filterState.age) {
                filters.push(`subject:${this.filterState.age}`);
            }
            if (this.filterState.year) {
                filters.push(`first_publish_year:${this.filterState.year}`);
            }
            return filters.join(' AND ');
        },
        bookRoomFeatures() {
            return {
                book3d: this.settingsState.styles.book.selected.startsWith('3d'),
                shelfLabel: this.settingsState.styles.shelfLabel.selected
            };
        },

        bookRoomClass() {
            return Object.entries(this.settingsState.styles)
                .map(([key, val]) => `style--${key}--${val.selected}`)
                .join(' ');
        }
    }
};
</script>

<style lang="less">
#app {
  font-family: "Avenir", Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
}

details[open] summary ~ * {
  animation: sweep .2s;
}

@keyframes sweep {
  0% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
}

.class-slider {
  margin-bottom: 5px;
}

hr {
  width: 100%;
}

.book-room {
  .class-slider .sections {
    background: rgba(255, 255, 255, .3);
    --highlight-color: rgba(255, 255, 255, .5);
    border-radius: 4px;
    height: 4px;
  }

  .book-end-start {
    display: none;
  }

  .book {
    position: relative;
  }

  .cover-label {
    background: rgba(0, 0, 0, .5);
    position: absolute;
    bottom: 0;
    font-size: .8em;
    opacity: .9;
    line-height: .8em;
    padding: 0;
  }
  .cover-label a {
    padding: 6px;
    color: white;
    text-decoration: underline;
  }
}

.book-room.style--book--spines {
  .book {
    animation: 200ms slide-in;
    transition: width .2s;
    transition-delay: .5s;
    width: 40px;
    margin: 0;
    overflow: hidden;
    flex-shrink: 0;
    overflow: hidden;
    margin-left: 1px;
  }

  .book img {
    width: 150px;
    margin-left: -40px;
    object-fit: cover;
    object-position: center;
    transition: margin-left .2s;
    transition-delay: .5s;
  }
  .book:hover img {
    margin-left: 0;
  }
  .book:hover {
    width: 150px;
  }
}

.book-room.style--shelf--visual {
  .book-end-start {
    display: block;
  }

  .shelf-carousel[data-short="000"] {
    background: url("https://images.unsplash.com/photo-1515524738708-327f6b0037a7?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60")
      rgba(0, 0, 0, .5) !important;
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="000"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1515524738708-327f6b0037a7?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60");
    background-position: center !Important;
  }
  .shelf-carousel[data-short="001"],
  .shelf-carousel[data-short="001"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1472289065668-ce650ac443d2?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60");
    background-position: 0 center !Important;
  }

  .shelf-carousel[data-short="002"],
  .shelf-carousel[data-short="002"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1457369804613-52c61a468e7d?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="002"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1457369804613-52c61a468e7d?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=60");
  }
  .shelf-carousel[data-short="003"] {
    background: url("https://images.unsplash.com/photo-1569766670290-f5581d3bb53f?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1379&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="003"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1569766670290-f5581d3bb53f?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1379&q=60");
  }
  .shelf-carousel[data-short="010"],
  .shelf-carousel[data-short="010"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1472173148041-00294f0814a2?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60");
  }
  .shelf-carousel[data-short="020"] {
    background: url("https://images.unsplash.com/photo-1507842217343-583bb7270b66?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1453&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="020"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1507842217343-583bb7270b66?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1453&q=60");
  }
  .shelf-carousel[data-short="030"] {
    background: url("https://images.unsplash.com/photo-1524402822060-94f4fb30f6ff?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1267&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="030"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1524402822060-94f4fb30f6ff?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1267&q=60");
  }
  .shelf-carousel[data-short="100"] {
    background: url("https://images.unsplash.com/photo-1593240637899-5fc06c754c2b?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=640&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="100"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1593240637899-5fc06c754c2b?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=640&q=60");
  }
  .shelf-carousel[data-short="110"] {
    background: url("https://images.unsplash.com/photo-1548691905-57c36cc8d935?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1349&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="110"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1548691905-57c36cc8d935?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1349&q=60");
  }
  .shelf-carousel[data-short="120"] {
    background: url("https://images.unsplash.com/photo-1527066579998-dbbae57f45ce?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=632&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="120"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1527066579998-dbbae57f45ce?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=632&q=60");
  }
  .shelf-carousel[data-short="130"] {
    background: url("https://images.unsplash.com/photo-1565492206137-0797f1ca6dc6?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="130"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1565492206137-0797f1ca6dc6?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=crop&w=1350&q=60");
  }
  .shelf-carousel[data-short="140"] {
    background: url("https://upload.wikimedia.org/wikipedia/commons/8/88/Narrenschiff_%281549%29.jpg")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="140"] .book-end-start {
    background: url("https://upload.wikimedia.org/wikipedia/commons/8/88/Narrenschiff_%281549%29.jpg");
  }
  .shelf-carousel[data-short="150"] {
    background: url("https://images.unsplash.com/photo-1582390644226-33bf6dd99cfc?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=60")
      rgba(0, 0, 0, .5);
    background-blend-mode: multiply;
  }
  .shelf-carousel[data-short="150"] .book-end-start {
    background: url("https://images.unsplash.com/photo-1582390644226-33bf6dd99cfc?ixlib=rb-1.2.1&auto=format&fit=crop&w=1350&q=60");
  }

  .shelf-carousel[data-short="001"] .book-end-start {
    width: 300px;
    -webkit-mask-image: linear-gradient(137deg, black 55%, transparent 60%);
    mask-image: linear-gradient(137deg, black 55%, transparent 60%);
    position: sticky;
    top: 0;
    left: 0;
    bottom: 0;
  }
  .shelf-carousel[data-short] .book-end-start {
    background-position: 0 0;
  }
  .shelf-carousel[data-short] {
    background-position: 0 0;
  }

  @media (max-width: 450px) {
    .book-end-start {
      position: static !Important;
    }
  }

  .shelf-carousel {
    background-size: cover;
  }
  .book-end-start {
    width: 200px;
    height: 100%;
    flex-shrink: 0;

    margin-right: -40px;
    z-index: 2;
    -webkit-mask-image: linear-gradient(to right, black 90%, transparent);
    mask-image: linear-gradient(to right, black 90%, transparent);
  }

  .book-end-start h3 {
    background: rgba(0, 0, 0, .3);
    color: white;
    font-family: Roboto;
    font-weight: 300;
    line-height: 1em;
    font-size: 1.6em;
    text-align: center;
    padding: 10px;
    text-shadow: 0 0 5px black;
  }
}

.book-room.style--book--3d,
.book-room.style--book--3d-spines,
.book-room.style--book--3d-flat {
  .cover {
    opacity: .8;
    transition: opacity .2s;
  }
  .book:hover .cover {
    opacity: 1;
  }
  .book:hover .book-3d.css-box {
    backface-visibility: hidden;
    transform: perspective(2000px) translate3d(-40px, 0, 100px) rotateY(-15deg);
  }

  .css-box,
  .css-box > * {
    transition-duration: .2s;
    transition-property: width, height, transform;
  }
}

.book-room.style--book--3d-spines {
  .book {
    margin-left: -100px;
  }

  .book:first-child .book-3d,
  .book-end-start + .book .book-3d {
    margin-left: 120px !important;
  }

  .book:hover {
    z-index: 1;
  }
}

.book-room.style--book--3d-flat {
  .css-box {
    transform: unset !important;
  }
  .book {
    transform: rotateX(20deg);
    transform-style: preserve-3d;
  }
  .books-carousel {
    perspective: 2000px;
  }
}

.book-room.style--aesthetic--wip {
  background: linear-gradient(180deg,#ebdfc5 100px, #dbbe9f 1600px,#cba37e 4800px);
  background-position: scroll;
  font-family: "bahnschrift", -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol";

  #app {
    // FIXME
    background: #ebdfc5;
  }

  .classification-short {
    opacity: .6;
  }
  .bookshelf-wrapper {
    margin-left: 140px;
    &:last-child {
      padding-right: 70px;
    }
  }
  .bookshelf {
    // background: linear-gradient(
    //   to bottom,
    //   #543721 0px,
    //   #5a3b23 10px,
    //   #7b5130 10px,
    //   #5f432d
    // );
    background: linear-gradient(
      to right,
      rgba(29, 5, 0, .5),
      rgba(61, 0, 0, .1) 20%,
      transparent,
      rgba(61, 0, 0, .1) 60%,
      rgba(29, 5, 0, .5)
    ),
      linear-gradient(
      to bottom,
      transparent 0,
      transparent 10px,
      rgba(255, 191, 0, .4) 10px,
      rgba(255, 191, 0, .1) 15px,
      transparent 50px
    ),
      linear-gradient(
      to bottom,
      #543721 0,
      #5a3b23 10px,
      #7b5130 10px,
      #5f432d
    );
    border: 0;
    padding: 10px;
    padding-top: 36px;
    box-sizing: border-box;
    color: white;
  }

  .bookshelf-name button {
    background: none;
    border: none;
    color: inherit;

    padding: 6px 8px;

    transition: background-color 0.2s;
    cursor: pointer;
  }

  .bookshelf-name button:hover {
    background: rgba(255, 255, 255, .1);
  }

  .shelf {
    display: flex;
    flex-direction: column-reverse;
    margin-bottom: 35px;
  }

  .shelf-carousel {
    border: 0;
    background-color: #563822;
    background-image: linear-gradient(
      to bottom,
      rgba(0, 0, 0, .36),
      #563822 50px
    );
    margin: 0;
  }

  .class-slider.shelf-label {
    border: 0;
    background: none;
    color: rgba(255, 255, 255, .9);
    font-weight: 150;
    margin: 0;
    min-height: 2em;
  }

  .shelf-label {
    background: none;
  }

  .class-slider.shelf-label small {
    display: none;
  }

  .shelf-label button {
    border: 0 !important;
    border-radius: 4px;
    transition: background-color .2s;
    cursor: pointer;
  }

  .shelf-label button:hover {
    background-color: rgba(255, 255, 255, .2);
  }
  .shelf-label .sections {
    height: 4px;
    bottom: 0;
  }
}
</style>
