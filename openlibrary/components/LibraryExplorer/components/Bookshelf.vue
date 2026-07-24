<template>
  <div
    ref="box"
    class="bookshelf"
  >
    <transition
      :name="transitionName"
      @before-leave="onBeforeLeave"
      @enter="onEnter"
      @after-enter="onAfterEnter"
    >
      <div
        :key="node.short || 'root'"
        class="bookshelf-content"
      >
        <Shelf
          v-for="lvl of node.children"
          :key="lvl.short"
          :parent="node"
          :node="lvl"
          :classification="classification"
          :expand-bookshelf="expandBookshelf"
          :labels="labels"
          :features="features"
          :filter="filter"
          :sort="sort"
          :hide-expand="hideExpand"
        />
      </div>
    </transition>
  </div>
</template>

<script>
import Shelf from './Shelf.vue';


export default {
    components: {
        Shelf
    },

    props: {
        classification: Object,
        node: Object,
        expandBookshelf: Function,
        labels: Array,
        features: Object,
        filter: String,
        sort: String,
        hideExpand: {
            type: Boolean,
            default: false,
        },
        // 'left' | 'right' -- which direction the *new* content should slide in from.
        // Only meaningful in genre mode (see transitionName): DDC/LCC's continuous
        // scroll-between-bookcases doesn't swap a single Bookshelf's `node` reactively
        // the way genre mode's top-nav-driven selection does, so this prop is simply
        // unused there.
        transitionDirection: {
            type: String,
            default: 'right',
        },
    },

    computed: {
        // Empty name -> Vue falls back to unstyled v-enter-active/v-leave-active
        // classes, which have no CSS transition applied here, so the swap is
        // instantaneous -- preserves DDC/LCC's existing (non-animated) drill-down feel
        // exactly, since only genre mode's alphabeticalTopNav classification opts in.
        transitionName() {
            return this.classification.alphabeticalTopNav ? `slide-${this.transitionDirection}` : '';
        },
    },

    methods: {
        // A genre switch can be a *huge* height difference (e.g. "All Genres" at ~20
        // shelves vs. one genre at 3) -- animating the container smoothly across that
        // whole range still reads as "the shelf is resizing", even once it's not buggy.
        // So instead of animating height at all, just make the box instantly tall enough
        // to fit BOTH the leaving and entering content for the duration of the slide (no
        // clipping either way, no visible resize), then settle to the real final height
        // only in onAfterEnter, once the leaving content is already gone and nothing
        // visible shifts.
        onBeforeLeave(el) {
            const box = this.$refs.box;
            if (!box) return;
            this._leavingHeight = box.offsetHeight;
            // The leave-active class sets position: absolute + top: 0 to pull this
            // element out of flow -- but an absolutely positioned element's containing
            // block is its ancestor's *padding* box, not its content box, so top: 0
            // snaps it flush against the padding edge, skipping straight past
            // .bookshelf's 36px top padding entirely (which the still-in-flow entering
            // content, unaffected by this, keeps respecting normally). That mismatch is
            // the "header jumps/squishes up" glitch -- an inline top here (which beats
            // the class's top: 0, inline style wins the cascade) corrects it back to
            // the same position it was already sitting in before it went absolute.
            el.style.top = getComputedStyle(box).paddingTop;
        },
        onEnter(el) {
            const box = this.$refs.box;
            if (!box) return;
            // .bookshelf (box) is box-sizing: border-box with its own top/bottom padding
            // (e.g. the wip aesthetic's 36px/10px) -- an explicit height on a border-box
            // element is the *total* box including padding, but el (the content div) has
            // none of its own, so el.offsetHeight alone under-counts by exactly that
            // padding.
            const boxStyle = getComputedStyle(box);
            const verticalPadding = parseFloat(boxStyle.paddingTop) + parseFloat(boxStyle.paddingBottom);
            const enteringHeight = el.offsetHeight + verticalPadding;
            box.style.height = `${Math.max(this._leavingHeight || 0, enteringHeight)}px`;
        },
        onAfterEnter() {
            const box = this.$refs.box;
            if (!box) return;
            box.style.height = '';
        },
    },
};
</script>

<style>
@keyframes bookshelf-appear {
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
  position: relative;
  overflow: hidden;
  border: 3px solid black;
  border-radius: 4px;
  background: black;
  flex-shrink: 0;
  z-index: 1;
  animation: bookshelf-appear .2s;

  transition-property: transform, opacity, filter;
  transition-duration: .2s;
  transform-origin: top center;
}

/* Genre mode's directional cross-slide: the bookcase frame (.bookshelf, above) never
   moves -- only its content swaps. The leaving content is pulled out of flow
   (position: absolute) so the entering content can take over the container's height
   immediately and the two visually cross over each other like sliding along one
   continuous shelf, rather than stacking or fading. Pure transform, no opacity --
   this should read as sliding out of view, not fading out. */
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform .22s cubic-bezier(.4, 0, .2, 1);
}
.slide-left-leave-active,
.slide-right-leave-active {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
}
.slide-right-enter-from {
  transform: translateX(100%);
}
.slide-right-leave-to {
  transform: translateX(-100%);
}
.slide-left-enter-from {
  transform: translateX(-100%);
}
.slide-left-leave-to {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .slide-left-enter-active,
  .slide-left-leave-active,
  .slide-right-enter-active,
  .slide-right-leave-active {
    transition: none;
  }
}
</style>
