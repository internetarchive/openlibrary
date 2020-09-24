<template>
  <div class="demo-b">
    <!-- <details>
      <summary>Bookshelves</summary>
      <ol>
        <li v-for="(bookshelf, i) of bookshelves" :key="i">{{bookshelf.name}}</li>
      </ol>
    </details>-->
    <!-- <ClassSlider class="bookshelf-name" :node="classification.root" /> -->
    <BookRoom :classification="classification" :features="features" :filter="filter"/>
  </div>
</template>

<script>
import BookRoom from './BookRoom';

export default {
    components: { BookRoom },
    props: {
        filter: {
            default: '',
            type: String
        },
        features: {
            default: () => ({ book3d: true, shelfLabel: 'slider' })
        },
        classification: Object
    }
};
</script>

<style>
.demo-b .class-slider .sections {
  background: rgba(255, 255, 255, .3);
  --highlight-color: rgba(255, 255, 255, .5);
  border-radius: 4px;
  height: 4px;
}
</style>
