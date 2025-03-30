<template>
  <CSSBox
    class="book-3d"
    :class="{skinny: finalThickness < 30 }"
    :width="finalWidth"
    :height="finalHeight"
    :thickness="finalThickness"
    :style="`--book-hue: ${hashHue}`"
  >
    <template #front>
      <FlatBookCover :book="book" @load.once="updateWithImageMetadata" :cover="cover"/>
    </template>
    <template #left v-if="finalThickness > 15">
      <div class="author" :style="`color: hsl(${hashHue + 60}, 25%, 65%)`">{{byline}}</div>
      <hr>
      <div
        class="title"
        :style="(finalThickness < 30) && `transform: translateX(${finalThickness/2}px) rotateZ(90deg);`"
      >{{book.title}}</div>
    </template>
  </CSSBox>
</template>

<script>
import CSSBox from './CSSBox.vue';
import FlatBookCover from './FlatBookCover.vue';
import { hashCode } from '../utils.js';

export default {
    components: { CSSBox, FlatBookCover },
    props: {
        width: {
            type: Number,
            default: 300
        },
        height: {
            type: Number,
            default: 200
        },
        thickness: {
            type: Number,
            default: 50
        },
        book: Object,
        /** @type {'image' | 'text'} */
        cover: String,
    },

    data() {
        return {
            finalWidth: this.width,
            finalHeight: this.height,
            finalThickness: this.book.number_of_pages_median ? Math.min(50, this.book.number_of_pages_median / 10) : this.thickness,
        };
    },
    methods: {
        updateWithImageMetadata(e) {
            this.finalHeight = e.target.height;
        },
    },

    computed: {
        byline() {
            return this.book.author_name
                ? this.book.author_name
                    .map(a => {
                        const parts = a.split(/\s+/g);
                        return parts[parts.length - 1];
                    })
                    .join(' ')
                : '';
        },

        hashHue() {
            return hashCode(this.book.key) % 360;
        },
    }
};
</script>

<style>
@keyframes spin {
  0% {
    transform: perspective(2000px) rotateY(0deg);
  }

  25% {
    transform: perspective(2000px) rotateY(360deg);
  }

  50% {
    transform: perspective(2000px) rotateX(0deg);
  }

  100% {
    transform: perspective(2000px) rotateX(360deg);
  }
}

.right-face {
  background: repeating-linear-gradient(
    to right,
    #f5deb3 0 1px,
    #c8a76c 3px 5px
  );
}

.bottom-face,
.top-face {
  background: repeating-linear-gradient(to top, #f5deb3 0 1px, #c8a76c 3px 5px);
}

.front-face img.cover {
  width: 100%;
  mask-image: linear-gradient(to right, transparent 0, black 6px);
}

.front-face,
.left-face,
.back-face {
  background: #222;
}

.front-face {
  background: linear-gradient(to right, #333, #555);
}

.left-face {
  background: linear-gradient(to right, #222 10%, #444 50%, #444 75%, #222);
  background: linear-gradient(to right,
    hsl(var(--book-hue), 20%, 10%) 10%,
    hsl(var(--book-hue), 22%, 20%) 50%,
    hsl(var(--book-hue), 22%, 20%) 75%,
    hsl(var(--book-hue), 20%, 10%));
  padding: 0 5px;
  padding-top: 20px;
  font-size: .8em;
  text-align: center;
  line-height: 1em;
  color: white;
}

.front-face .author,
.left-face .author {
  font-size: .75em;
  text-transform: uppercase;
  font-family: Roboto, sans-serif;
  color: #B60;
}

.left-face .title {
  font-size: .75em;
}
.left-face .title {
  font-family: Georgia, serif;
  font-style: oblique;
}
.book-3d.skinny .left-face .title {
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
  overflow: clip;
  width: 150px;
  transform-origin: 0 0;
}

.book-3d div.cover {
  height: 100%;
}

.left-face hr {
  width: 50%;
  margin: 5px auto;
  border: 0;
  opacity: 0.8;
  background: transparent;
  border-bottom: 2px dotted white;
  border-color: hsl(var(--book-hue), 70%, 60%);
}
</style>
