<template>
  <img
    v-if="coverMultiresUrl"
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
        book: Object
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
}
</style>
