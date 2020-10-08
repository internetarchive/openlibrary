<template>
  <div class="book-room" :class="{'expanding-animation': expandingAnimation}">
    <div class="room-breadcrumbs" style="position: absolute; transform: translateY(-20px)">
      <span v-for="(node, i) of breadcrumbs" :key="i">
        <button @click="goUpTo(i)">{{i == 0 ? 'Home' : node.name}}</button>
        &gt;
      </span>
      <span v-if="breadcrumbs.length">{{activeRoom.name}}</span>
    </div>
    <div class="bookshelf-signage">
      <div v-if="signState.left" class="bookshelf-signage--sign bookshelf-signage--lr-sign">
        <RightArrowIcon style="transform: rotate(-180deg)"/>
        <div class="sign-classification">{{signState.left.short}}</div>
        <div class="sign-label">{{signState.left.name}}</div>
      </div>
      <div class="bookshelf-signage--center-sign">
        <div v-if="signState.parent" class="bookshelf-signage--sign bookshelf-signage--breadcrumb-sign">
          <div class="sign-classification">{{signState.parent.short}}</div>
          <div class="sign-label">{{signState.parent.name}}</div>
        </div>
        <div class="bookshelf-signage--sign bookshelf-signage--main-sign">
          <div class="sign-classification">{{signState.main.short}}</div>
          <div class="sign-label">{{signState.main.name}}</div>
        </div>
      </div>
      <div v-if="signState.right" class="bookshelf-signage--sign bookshelf-signage--lr-sign">
        <RightArrowIcon/>
        <div class="sign-classification">{{signState.right.short}}</div>
        <div class="sign-label">{{signState.right.name}}</div>
      </div>
    </div>
    <div class="book-room-shelves" @scroll.passive="updateActiveShelfOnScroll">
      <!-- <ClassSlider class="bookshelf-name" :node="classification.root" /> -->
      <div class="bookshelf-wrapper" v-for="(bookshelf, i) of activeRoom.children" :key="i">
        <transition-group>
          <div class="bookshelf bookshelf-back" v-for="node in breadcrumbs" :key="node.name"></div>
        </transition-group>
        <div class="bookshelf" :id="bookshelf.short">
          <div class="bookshelf-name">
            <h2>
              <span class="classification-short">{{bookshelf.short}}</span>
              {{bookshelf.name}}
            </h2>
            <button @click="expandBookshelf(bookshelf)" v-if="activeRoom.children">
              <ExpandIcon/>
            </button>
          </div>
          <div class="shelf" v-for="(lvl, i) of bookshelf.children" :key="i" :id="lvl.short">
            <OLCarousel
              class="shelf-carousel"
              :data-short="lvl.children && lvl.position != 'root' ? lvl.children[lvl.position].short : lvl.short"
              :query="`${lvl.children && lvl.position != 'root' ? lvl.children[lvl.position].query : lvl.query} ${filter}`"
              :node="lvl.children  && lvl.position != 'root' ? lvl.children[lvl.position] : lvl"
            >
              <template #book-end-start>
                <div class="book-end-start">
                  <h3>{{lvl.children && lvl.position != 'root' ? lvl.children[lvl.position].name : lvl.name}}</h3>
                </div>
              </template>

              <template v-slot:cover="{book}" v-if="features.book3d">
                <BookCover3D :width="150" :height="200" :thickness="50" :book="book"/>
              </template>

              <template v-slot:cover-label="{book}">
                <span
                  v-if="book[classification.field]"
                  :title="book[classification.field].map(classification.fieldTransform).join('\n')"
                >{{classification.fieldTransform(book[classification.field][0])}}</span>
              </template>
            </OLCarousel>

            <ClassSlider
              v-if="features.shelfLabel == 'slider'"
              class="shelf-label"
              :node="lvl"
              :key="i"
            />
            <ShelfLabel v-else :node="lvl" :key="i">
              <template #extra-actions>
                <button title="Expand shelf" @click="expandBookshelf(bookshelf)">
                  <ExpandIcon/>
                </button>
              </template>
            </ShelfLabel>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import OLCarousel from './OLCarousel';
import ClassSlider from './ClassSlider';
import ShelfLabel from './ShelfLabel';
import BookCover3D from './BookCover3D';
import ExpandIcon from './icons/ExpandIcon.vue';
import RightArrowIcon from './icons/RightArrowIcon.vue';

export default {
    components: {
        OLCarousel,
        ClassSlider,
        BookCover3D,
        ShelfLabel,
        ExpandIcon,
        RightArrowIcon
    },
    props: {
        classification: Object,
        appSettings: Object,

        filter: {
            default: '',
            type: String
        },
        features: {
            default: () => ({
                book3d: true,
                shelfLabel: 'slider'
            })
        }
    },
    watch: {
        classification(newVal, oldVal) {
            this.activeRoom = newVal.root;
            this.breadcrumbs = [];
        }
    },
    data() {
        return {
            activeRoom: this.classification.root,
            breadcrumbs: [],

            expandingAnimation: false,

            roomWidth: 1,
            viewportWidth: 1,
            activeBookcaseIndex: 0,
        };
    },

    created() {
        window.addEventListener('resize', this.updateWidths, { passive: true });
    },
    mounted() {
        this.updateWidths();
    },
    destroyed() {
        window.removeEventListener('resize', this.updateWidths);
    },

    computed: {
        signState() {
            const cases = this.activeRoom.children;
            const i = this.activeBookcaseIndex;

            return {
                left: cases[i - 1],
                main: cases[i],
                right: cases[i + 1],
                parent: this.breadcrumbs.length && this.activeRoom,
            };
        }
    },
    methods: {
        async expandBookshelf(bookshelf) {
            this.expandingAnimation = true;
            await new Promise(r => setTimeout(r, 200));
            this.expandingAnimation = false;
            this.breadcrumbs.push(this.activeRoom);
            this.activeRoom = bookshelf;
        },
        goUpTo(index) {
            this.activeRoom = this.breadcrumbs[index];
            this.breadcrumbs.splice(index, this.breadcrumbs.length - index);
        },

        updateWidths() {
            const { max } = Math;
            // Avoid dividing by 0 and whatnot
            this.roomWidth = max(1, this.$el.querySelector('.book-room-shelves').scrollWidth);
            this.viewportWidth = max(1, this.$el.getBoundingClientRect().width);

            if (this.roomWidth == 1 || this.viewportWidth == 1) {
                console.log("RECOMPUTING WIDTH");
                setTimeout(this.updateWidths, 100);
            }
        },

        updateActiveShelfOnScroll(ev) {
            const scrollCenterX = ev.target.scrollLeft + this.viewportWidth / 2;
            const shelves = this.activeRoom.children;
            const shelvesCount = shelves.length;
            this.activeBookcaseIndex =  Math.floor(shelvesCount * (scrollCenterX / this.roomWidth));
        }
    }
};
</script>

<style lang="less">
.bookshelf-signage {
  display: flex;
  width: 100%;

  &--center-sign {
    flex: 1;
  }

  &--lr-sign {
    min-width: 150px;
    width: 25%;
    margin: 4px;
    align-self: flex-end;
    line-height: 1em;

    svg {
      padding: .5em .2em;
    }
    &:first-child svg {
      float: left;
    }
    &:last-child svg {
      float: right;
    }
  }

  &--sign {
    background: #1a1a1a;
    color: white;
    padding: 10px;
    box-sizing: border-box;

    .sign-classification {
      opacity: .5;
      font-size: .9em;
    }
  }

  &--center-sign {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;

    .bookshelf-signage--sign {
      min-width: 400px;
      max-width: 500px;
    }
  }

  &--breadcrumb-sign {
    transform-origin: bottom center;
    transform: scale(.85);
    opacity: .8;

    div {
      display: inline-block;
    }
    .sign-label {
      margin-left: 1em;
    }
  }

  &--main-sign {
    padding: 20px 30px;

    & .sign-label {
      font-size: 1.3em;
    }
  }
}

.bookshelf-signage {
  display: none;
}

.book-room.expanding-animation .bookshelf {
  transform: scale(.8);
  opacity: .9;
  filter: brightness(.6);
}
.book-room-shelves {
  display: flex;
  overflow-x: auto;
  -webkit-scroll-snap-type: x mandatory;
  scroll-snap-type: x mandatory;
}

.bookshelf-wrapper {
  width: 900px;
  max-width: 100%;
  margin: 0 30px;
  -webkit-scroll-snap-align: center;
  scroll-snap-align: center;
  position: relative;
  flex-shrink: 0;
}

@keyframes shelf-appear {
  from {
    opacity: 0;
    transform: scale(1.5);
  }
  from {
    opacity: 1;
    transform: scale(1);
  }
}

.bookshelf {
  border: 3px solid black;
  border-radius: 4px;
  background: black;
  flex-shrink: 0;
  z-index: 1;
  animation: shelf-appear .2s;

  transition-property: transform, opacity, filter;
  transition-duration: .2s;
  transform-origin: top center;
}

.bookshelf.bookshelf-back {
  height: 30px;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  transition-property: transform, opacity, filter;
  transition-duration: .2s;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;

  transform: scale(.8) translateY(-30px);
  opacity: .9;
  filter: brightness(.6);

  &.v-enter,
  &.v-leave-to {
    transform: initial;
    filter: initial;
    opacity: 0;
  }
}

.bookshelf-name {
  max-width: 800px;
  margin: auto;
  text-align: center;
  color: white;

  margin: 20px 0;
}

.bookshelf-name h2 {
  color: white;
  font-weight: 300;
  font-size: 1.5em;
}

.shelf-label {
  border-radius: 0;
  background: white;
  /* color: white; */

  /* --highlight-color: rgba(255,255,0, 0.2); */
}

.shelf-carousel {
  border: 3px solid black;
  margin-top: 10px;
  border-radius: 4px;
  height: 285px;
  background: #EEE;
}

.book {
  justify-content: flex-end;
  margin-bottom: 10px;
}

.book:first-child .book-3d,
.book-end-start + .book .book-3d {
  margin-left: 20px;
}

.shelf-label {
  background: black;
  color: white;
}
</style>
