<template>
  <img
    v-if="cover == 'image' && coverMultiresUrl"
    class="cover"
    loading="lazy"
    @load="$emit('load', $event)"
    :title="book.title"
    :src="coverMultiresUrl.medium"
    :srcset="`${coverMultiresUrl.large} 2x`"
  >
  <div v-else class="cover">
    <div class="title">{{book.title}}</div>
    <hr>
    <div class="author">{{byline}}</div>
  </div>
</template>


<script>
import CONFIGS from '../configs';

export default {
    props: {
        book: Object,
        /** @type {'image' | 'text'} */
        cover: {
            default: 'image'
        }
    },

    computed: {
        byline() {
            return this.book.author_name ? this.book.author_name.join(' ') : '';
        },

        coverMultiresUrl() {
            const { cover_i, lending_edition_s } = this.book;
            const fullUrl = lending_edition_s ? this.olCoverUrl(lending_edition_s, 'olid') :
                cover_i && cover_i != -1 ? this.olCoverUrl(cover_i) :
                    null;

            if (fullUrl) {
                return {
                    small: fullUrl.replace('.jpg', '-S.jpg'),
                    medium: fullUrl.replace('.jpg', '-M.jpg'),
                    large: fullUrl.replace('.jpg', '-L.jpg'),
                    full: fullUrl,
                };
            } else {
                return undefined;
            }
        },
    },

    methods: {
        /**
         * @param {String} id
         * @param {'id' | 'olid'} idType
         */
        olCoverUrl(id, idType='id') {
            return `${CONFIGS.OL_BASE_COVERS}/b/${idType}/${id}.jpg`;
        }
    }
};
</script>

<style scoped>
div.cover {
  height: 100%;
  padding: 5px;
  box-sizing: border-box;
  background: #333;
  color: white;
  flex-direction: column;
  justify-content: center;

  padding: 5px;
  box-sizing: border-box;
  background: linear-gradient(to right, #333, #222 5px, #333 10px);
  color: white;
  flex-direction: column;
  justify-content: center;
}

.title {
  padding: 0 10px;
  font-family: Georgia, serif;
  font-style: oblique;
}

.author {
  font-size: .75em;
  text-transform: uppercase;
  font-family: Roboto, Helvetica, sans-serif;
  color: #B60;
}

hr {
  border-left: 20px solid transparent;
  border-right: 20px solid transparent;
  box-sizing: border-box;
}
</style>
