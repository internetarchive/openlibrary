<template>
  <div class="book-room" :class="{'expanding-animation': expandingAnimation}">
    <div class="room-breadcrumbs" style="position: absolute; transform: translateY(-20px)">
      <span v-for="(node, i) of breadcrumbs" :key="i">
        <button @click="goUpTo(i)">{{i == 0 ? 'Home' : node.name}}</button>
        &gt;
      </span>
      <span v-if="breadcrumbs.length">{{activeRoom.name}}</span>
    </div>
    <div class="book-room-shelves" @scroll.passive="updateActiveShelfOnScroll">
      <div class="bookshelf-wrapper" v-for="(bookshelf, i) of activeRoom.children" :key="i">
        <div class="bookshelf-name-wrapper">
          <component class="bookshelf-name bookshelf-signage--sign"
            :is="signState.left == bookshelf || signState.right == bookshelf ? 'button': 'div'"
            @click="moveToShelf(i)"
            :class="{
              'bookshelf-signage--lr-sign': signState.left == bookshelf || signState.right == bookshelf,
              'right': signState.right == bookshelf,
              'left': signState.left == bookshelf,
              'bookshelf-signage--center-sign': signState.left != bookshelf && signState.right != bookshelf,
            }"
          >
              <main class="sign-body">
                <RightArrowIcon class="arrow-icon" />
                <div class="sign-classification">{{bookshelf.short}}</div>
                <div class="sign-label">{{bookshelf.name}}</div>
              </main>
              <div class="sign-toolbar">
                <button @click="expandBookshelf(bookshelf)" v-if="bookshelf.children && bookshelf.children[0].children" title="Expand">
                  <ExpandIcon /> <span class="label">See more</span>
                </button>
              </div>
          </component>
        </div>

        <transition-group>
          <div class="bookshelf bookshelf-back" v-for="node in breadcrumbs" :key="node.name || 'root'"></div>
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
import ExpandIcon from './icons/ExpandIcon.vue';

export default {
    components: {
        Bookshelf,
        RightArrowIcon,
        ExpandIcon,
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
.bookshelf-signage {
  &--sign {
    background: #232323;
    color: white;
    box-sizing: border-box;

    .sign-classification {
      opacity: .5;
      font-size: .9em;
    }
  }

  &--lr-sign {
    max-width: 300px;
    margin: 4px;
    align-self: flex-end;
    line-height: 1em;
    position: fixed;
    padding: 14px;
    z-index: 4;
    top: 50px;

    border: 0;
    &:hover {
      background: lighten(#232323, 5%);
    }

    @media (min-width: 450px) {
      min-width: 150px;
      width: 25%;
    }
    @media (max-width: 450px) {
      .sign-label, .sign-classification { display: none; }
      top: 75%;
    }

    &.left {
      left: 0;
      .sign-body .arrow-icon {
        float: left;
        transform: rotateZ(-180deg);
        margin-right: 8px;
      }
    }

    &.right {
      right: 0;
      .sign-body .arrow-icon { float: right; }
    }

    .sign-toolbar { display: none; }

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
        font-size: 0.7em;
        opacity: 0.95;
      }

      .label {
        margin-left: 8px;
      }

      svg {
        height: 14px;
        width: 14px;
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
