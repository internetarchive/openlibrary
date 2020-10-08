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

        <Bookshelf
          :node="bookshelf"
          :expandBookshelf="expandBookshelf"
          :features="features"
          :classification="classification"
          :filter="filter"
        />
      </div>
    </div>
  </div>
</template>

<script>

import Bookshelf from './Bookshelf.vue';
import RightArrowIcon from './icons/RightArrowIcon.vue';

export default {
    components: {
        Bookshelf,
        RightArrowIcon,
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
</style>
