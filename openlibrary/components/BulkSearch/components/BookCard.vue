<template>

<div class="book-card">
          <div class="cover">
            <img :src="coverImage">
          </div>
          <div class="info">
            <a class="title" :href="workUrl" target="_blank">{{ doc.title }}</a>
            <div class="byline">{{ doc.author_name[0] }}</div>

            <div class="identifier">{{doc.first_publish_year}} - {{doc.edition_count}} editions</div>
            <a class="action actionName" target="_blank"></a>
          </div>
</div>


</template>



<script>

export default {
    props: {
        doc: Object
    },
    computed: {
        coverImage() {
            if (!this.doc.cover_i){
                return ''
            }
            return `https://covers.openlibrary.org/b/id/${this.doc.cover_i}-M.jpg`
        },
        workUrl() {
            return `https://openlibrary.org/books/${this.doc.key.split('/')[2]}`
        }
    }
}</script>


<style>

@keyframes pulse {
    0% { opacity: 0; }
    100% { opacity: 0.95; }
}

@keyframes slideUp {
    0% { transform: translateY(50%); opacity: 0.5; }
    100% { transform: translateY(0); opacity: 1; }
}

@keyframes shiftRight {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(0); }
}
.book-card {
  background: white;
  flex-shrink: 0;
  margin-right: 6px;
  width: 80vw;
  max-width: 300px;
  height: 120px;
  border: 1px solid #AAA;
  border-radius: 4px;
  display: flex;
  overflow: hidden;
  color: inherit;
  text-decoration: inherit;
  position: relative;
  transition-property: background-color border-color;
  transition-duration: 0.2s;

  &:first-child {
    animation: slideUp .8s;
  }

  &:nth-child(2) {
    animation: shiftRight .8s;
  }

  &:hover {
    background: rgba(0,0,255,0.05);
    border-color: rgba(0,0,255,0.5);
  }

  &.loading::before {
    content: "";
    position: absolute;
    width: 6px;
    height: 6px;
    border-radius: 100px;
    margin: 10px;
    right: 0;
    background: blue;
    opacity: 0;
    animation: pulse 0.5s infinite alternate;
    animation-delay: .5s;
  }

  .action {
    padding: 4px;
    background: rgba(0,0,255,0.6);
    border-radius: 4px;
    color: white;
    text-decoration: none;
    margin-top: 4px;
    display: inline-block;
  }
  .action:empty { display: none; }

  .title {
    font-weight: bold;
    font-size: 1.1em;
    line-height: 1;

    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    overflow: hidden;
  }
  .cover {
    width: 25%;
    img { width: 100%; height: 100%; object-fit: cover; }
  }
  .identifier {
    margin-top: 4px;
    padding-top: 4px;
    color: #555;
    border-top: 1px dotted;
    flex: 1;
  }

  .info {
    flex: 1;
    padding: 8px;
  }
}
</style>
