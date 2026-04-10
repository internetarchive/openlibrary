<template>
  <div
    class="book-card"
    :class="{ 'book-card--primary': isPrimary, 'book-card--secondary': !isPrimary }"
  >
    <div class="cover">
      <img
        :src="coverImage"
        loading="lazy"
      >
    </div>
    <div class="info">
      <a
        class="title"
        :href="workUrl"
        target="_blank"
      >{{ doc.title }}</a>
      <div class="byline">
        {{ doc.author_name[0] }}
      </div>
      <div class="identifier">
        {{ doc.first_publish_year }} - {{ doc.edition_count }} editions
      </div>
      <a
        class="action actionName"
        target="_blank"
      />
    </div>
  </div>
</template>

<script>
export default {
    props: {
        doc: Object,
        isPrimary: {
            type: Boolean,
            default: false
        }
    },
    computed: {
        coverImage() {
            if (!this.doc.cover_i) {
                return ''
            }
            return `https://covers.openlibrary.org/b/id/${this.doc.cover_i}-M.jpg`
        },
        workUrl() {
            return `https://openlibrary.org/${this.doc.key}`
        }
    }
}</script>


<style>
@keyframes pulse {
  0% {
    opacity: 0;
  }

  100% {
    opacity: 0.95;
  }
}

@keyframes slideUp {
  0% {
    transform: translateY(50%);
    opacity: 0.5;
  }

  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes shiftRight {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(0);
  }
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
  transition-property: background-color border-color opacity;
  transition-duration: 0.2s;
}

.book-card:first-child {
  animation: slideUp .8s;
}

.book-card:nth-child(2) {
  animation: shiftRight .8s;
}

.book-card:hover {
  background: rgba(0, 0, 255, 0.05);
  border-color: rgba(0, 0, 255, 0.5);
}

.book-card.book-card--primary {
  border: 1px solid rgba(0, 0, 255, 0.5);
}

.book-card.loading::before {
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

.book-card .action {
  padding: 4px;
  background: rgba(0, 0, 255, 0.6);
  border-radius: 4px;
  color: white;
  text-decoration: none;
  margin-top: 4px;
  display: inline-block;
}

.book-card .action:empty {
  display: none;
}

.book-card .title {
  font-weight: bold;
  font-size: 1.1em;
  line-height: 1;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.book-card .cover {
  width: 25%;
}

.book-card .cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.book-card .identifier {
  margin-top: 4px;
  padding-top: 4px;
  color: #555;
  border-top: 1px solid #D8D8D8;
  flex: 1;
}

.book-card .info {
  flex: 1;
  padding: 8px;
}
</style>
