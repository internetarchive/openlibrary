<template>
  <div class="book-room" :class="{'expanding-animation': expandingAnimation}">
    <!-- <div class="room-breadcrumbs">
      <span v-for="(node, i) of breadcrumbs" :key="i">
        <button @click="goUpTo(i)">{{i == 0 ? 'Home' : node.name}}</button>
        &gt;
      </span>
      <span v-if="breadcrumbs.length">{{activeRoom.name}}</span>
    </div> -->
    <div class="lr-signs">
      <button
        class="bookshelf-name bookshelf-signage--sign bookshelf-signage--lr-sign left"
        v-if="signState.left"
        @click="moveToShelf(activeBookcaseIndex - 1)"
      >
        <main class="sign-body">
          <RightArrowIcon class="arrow-icon" />
          <div class="sign-classification">{{signState.left.short}}</div>
          <div class="sign-label">{{signState.left.name}}</div>
        </main>
      </button>
      <!-- Gap --> <div style="flex: 1" />
      <button
        class="bookshelf-name bookshelf-signage--sign bookshelf-signage--lr-sign right"
        v-if="signState.right"
        @click="moveToShelf(activeBookcaseIndex + 1)"
      >
        <main class="sign-body">
          <RightArrowIcon class="arrow-icon" />
          <div class="sign-classification">{{signState.right.short}}</div>
          <div class="sign-label">{{signState.right.name}}</div>
        </main>
      </button>
    </div>
    <div class="book-room-shelves" ref="scrollingElement" @scroll.passive="updateActiveShelfOnScroll">
      <div class="bookshelf-wrapper" v-for="(bookshelf, i) of activeRoom.children" :key="i" :data-short="bookshelf.short">
        <div class="bookshelf-name-wrapper">
          <div class="bookshelf-name bookshelf-signage--sign bookshelf-signage--center-sign">
              <main class="sign-body">
                <div class="sign-classification">{{bookshelf.short}}</div>
                <div class="sign-label">{{bookshelf.name}}</div>
              </main>
              <div class="sign-toolbar">
              <button
                  v-if="breadcrumbs.length"
                  @click="goUpTo(breadcrumbs.length - 1)"
                >
                  <RightArrowIcon style="transform: rotate(-90deg)" /> <span class="label">Go up</span>
                </button>
                <!-- Gap --> <div style="flex: 1" />
                <button @click="expandBookshelf(bookshelf)" v-if="bookshelf.children && bookshelf.children[0].children" title="Expand">
                  <ExpandIcon /> <span class="label">See more</span>
                </button>
              </div>
          </div>
        </div>

        <transition-group>
          <div class="bookshelf bookshelf-back" v-for="node in breadcrumbs" :key="node.name || 'root'"></div>
        </transition-group>

        <Bookshelf
          :node="bookshelf"
          :expandBookshelf="expandBookshelf"
          :features="features"
          :classification="classification"
          :labels="appSettings.labels"
          :filter="filter"
          :sort="sort"
        />
      </div>
      <!-- Gap --> <div style="width: 70px; height: 1px; flex-shrink: 0" />
    </div>
  </div>
</template>

<script>
import Bookshelf from './Bookshelf.vue';
import RightArrowIcon from './icons/RightArrowIcon.vue';
import ExpandIcon from './icons/ExpandIcon.vue';
import debounce from 'lodash/debounce';
import Vue from 'vue';

export default {
    components: {
        Bookshelf,
        RightArrowIcon,
        ExpandIcon,
    },
    props: {
        classification: Object,
        appSettings: Object,

        sort: String,
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
        async classification(newVal) {
            this.activeRoom = newVal.root;
            this.breadcrumbs = [];
            await Vue.nextTick();
            this.updateWidths();
            this.updateActiveShelfOnScroll();
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
        this.debouncedUpdateWidths = debounce(this.updateWidths);
        window.addEventListener('resize', this.debouncedUpdateWidths, { passive: true });
    },
    mounted() {
        this.updateWidths();
    },
    destroyed() {
        window.removeEventListener('resize', this.debouncedUpdateWidths);
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
        async expandBookshelf(bookshelf, shelf=null) {
            this.expandingAnimation = true;
            await new Promise(r => setTimeout(r, 200));
            this.expandingAnimation = false;
            this.breadcrumbs.push(this.activeRoom);
            this.activeRoom = bookshelf;
            const nodeToScrollTo = shelf?.position == 'root' ? shelf :
                shelf?.children && shelf?.position ? shelf.children[shelf.position]
                    : (shelf || bookshelf);
            await Vue.nextTick();
            this.$el.querySelector(`[data-short="${nodeToScrollTo.short}"]`).scrollIntoView();
        },

        async goUpTo(index) {
            const nodeToScrollTo = this.activeRoom;
            this.activeRoom = this.breadcrumbs[index];
            this.breadcrumbs.splice(index, this.breadcrumbs.length - index);
            await Vue.nextTick();
            this.$el.querySelector(`[data-short="${nodeToScrollTo.short}"]`).scrollIntoView();
        },

        updateWidths() {
            const { max } = Math;
            // Avoid dividing by 0 and whatnot
            this.roomWidth = max(1, this.$el.querySelector('.book-room-shelves').scrollWidth);
            this.viewportWidth = max(1, this.$el.getBoundingClientRect().width);

            if (this.roomWidth == 1 || this.viewportWidth == 1) {
                setTimeout(this.updateWidths, 100);
            }
        },

        updateActiveShelfOnScroll() {
            const scrollCenterX = this.$refs.scrollingElement.scrollLeft + this.viewportWidth / 2;
            const shelves = this.activeRoom.children;
            const shelvesCount = shelves.length;
            this.activeBookcaseIndex =  Math.floor(shelvesCount * (scrollCenterX / this.roomWidth));
        },

        moveToShelf(index) {
            this.$el.querySelector(`.bookshelf-wrapper:nth-child(${index + 1})`)
                .scrollIntoView({
                    behavior: 'smooth',
                    inline: 'center',
                    block: 'nearest'
                });
        },
    }
};
</script>

<style lang="less">
button {
  font-family: inherit;
  text-align: inherit;
  cursor: pointer;
  transition: background-color 0.2s;
}

.bookshelf-name {
  margin: 0 auto;
  margin-bottom: 40px;
}

.lr-signs {
  position: sticky;
  top: 10px;
  pointer-events: none;
  z-index: 10;
  display: flex;

  @media (max-width: 450px) {
    top: 75%;
  }
}
.bookshelf-signage {
  &--sign {
    background: #232323;
    color: white;
    box-sizing: border-box;
    border-radius: 4px;
    overflow: hidden;

    .sign-classification {
      opacity: .5;
      font-size: .9em;
    }
  }

  &--lr-sign {
    max-width: 300px;
    margin: 0;
    line-height: 1em;
    padding: 14px;
    pointer-events: all;

    border: 0;
    &:hover {
      background: lighten(#232323, 5%);
    }


    &.left .sign-body .arrow-icon {
      float: left;
      transform: rotateZ(-180deg);
      margin-right: 8px;
    }

    &.right .sign-body .arrow-icon { float: right; }

    @media (min-width: 450px) {
      min-width: 150px;
      width: 25%;
      margin: 4px;
    }
    @media (max-width: 450px) {
      .sign-label, .sign-classification { display: none; }
      &.left .sign-body .arrow-icon { margin-right: 0; }
    }

    .sign-toolbar { display: none; }

    .sign-label {
      text-overflow: ellipsis;
      overflow: hidden;
      white-space: nowrap;
    }

    svg {
      padding: .5em .2em;
    }
  }

  &--center-sign {
    display: flex;
    flex-direction: column;


    max-width: 500px;
    min-height: 124px;
    width: 100%;

    @media (min-width: 450px) {
      min-width: 400px;
    }
    .sign-body .arrow-icon { display: none; }

    .sign-body { flex: 1; }
    .sign-label { font-size: 1.3em; }

    padding-top: 20px;
    .sign-toolbar {
      background: #2c2c2c;
      display: flex;
      flex-direction: row;
      justify-content: flex-end;

      button {
        font-size: 0.75em;
        opacity: 0.95;
      }
      .label {
        margin-left: 3px;
      }

      svg {
        height: 14px;
        width: 14px;
        margin-bottom: -2px;
      }
    }

    .sign-classification, .sign-label {
      padding: 0 25px;
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

.bookshelf-name-wrapper {
  height: 190px;
  display: flex;
  align-items: flex-end;
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

.bookshelf.bookshelf-back {
  height: 30px;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  transition-property: transform, opacity, filter;
  transition-duration: .2s;

  transform: scale(.8) translateY(12px);
  opacity: .9;
  filter: brightness(.6);

  &.v-enter,
  &.v-leave-to {
    transform: initial;
    filter: initial;
    opacity: 0;
  }
}
</style>
