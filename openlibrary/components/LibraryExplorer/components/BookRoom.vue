<template>
  <div
    class="book-room"
    :class="{'expanding-animation': expandingAnimation, 'genre-mode': classification.alphabeticalTopNav}"
    @touchstart.passive="onShelvesTouchStart"
    @touchend="onShelvesTouchEnd"
  >
    <!-- <div class="room-breadcrumbs">
      <span v-for="(node, i) of breadcrumbs" :key="i">
        <button @click="goUpTo(i)">{{i === 0 ? 'Home' : node.name}}</button>
        &gt;
      </span>
      <span v-if="breadcrumbs.length">{{activeRoom.name}}</span>
    </div> -->
    <!-- Genre mode's "home" scroll-snap anchor: a zero-height, always-present, NON-sticky
         sentinel at the very top of the scroll pane. Home must snap to scrollTop 0 (nav +
         filter + first shelf visible), but it can't be anchored to the nav (sticky: its snap
         position tracks where it's stuck, so scrolling up collapses home onto the first
         shelf) or the filter (renders late via v-if, so it isn't a snap target on first
         paint). This sentinel is neither -- a stable snap position fixed at 0. -->
    <div
      v-if="classification.alphabeticalTopNav"
      class="genre-scroll-home"
      aria-hidden="true"
    />
    <GenreTopNav
      v-if="classification.alphabeticalTopNav"
      :nodes="classification.root.children"
      :active-index="activeGenreIndex"
      @select="selectGenre"
      @select-all="selectAllGenres"
    />
    <GenreFilterBar
      v-if="classification.alphabeticalTopNav"
      :filter-state="filterState"
      :sort-state="sortState"
    />
    <div
      v-else
      class="lr-signs"
    >
      <button
        v-if="signState.left"
        class="bookshelf-name bookshelf-signage--sign bookshelf-signage--lr-sign left"
        @click="moveToShelf(activeBookcaseIndex - 1)"
      >
        <main class="sign-body">
          <RightArrowIcon class="arrow-icon" />
          <div class="sign-classification">
            {{ signState.left.short }}
          </div>
          <div class="sign-label">
            {{ signState.left.name }}
          </div>
        </main>
      </button>
      <!-- Gap --> <div style="flex: 1" />
      <button
        v-if="signState.right"
        class="bookshelf-name bookshelf-signage--sign bookshelf-signage--lr-sign right"
        @click="moveToShelf(activeBookcaseIndex + 1)"
      >
        <main class="sign-body">
          <RightArrowIcon class="arrow-icon" />
          <div class="sign-classification">
            {{ signState.right.short }}
          </div>
          <div class="sign-label">
            {{ signState.right.name }}
          </div>
        </main>
      </button>
    </div>
    <div
      ref="scrollingElement"
      class="book-room-shelves"
      @scroll.passive="updateActiveShelfOnScroll"
    >
      <div
        v-for="(bookshelf, i) of bookcases"
        :key="i"
        class="bookshelf-wrapper"
        :data-short="bookshelf.short"
      >
        <template v-if="!classification.alphabeticalTopNav">
          <div class="bookshelf-name-wrapper">
            <div class="bookshelf-name bookshelf-signage--sign bookshelf-signage--center-sign">
              <main class="sign-body">
                <div class="sign-classification">
                  {{ bookshelf.short }}
                </div>
                <div class="sign-label">
                  {{ bookshelf.name }}
                </div>
              </main>
              <div class="sign-toolbar">
                <button
                  v-if="breadcrumbs.length"
                  @click="goUpTo(breadcrumbs.length - 1)"
                >
                  <RightArrowIcon style="transform: rotate(-90deg)" /> <span class="label">Go up</span>
                </button>
                <!-- Gap --> <div style="flex: 1" />
                <button
                  v-if="bookshelf.children && bookshelf.children[0].children"
                  title="Expand"
                  @click="expandBookshelf(bookshelf)"
                >
                  <ExpandIcon /> <span class="label">See more</span>
                </button>
              </div>
            </div>
          </div>

          <transition-group>
            <div
              v-for="node in breadcrumbs"
              :key="node.name || 'root'"
              class="bookshelf bookshelf-back"
            />
          </transition-group>
        </template>

        <!-- Genre mode: exactly one bookcase, always -- "All Genres" is one shelf per
             top-level genre, a specific genre is one shelf per subgenre. Selection (via
             the top nav above, not scrolling/expanding) is the only way to change what's
             shown here, so the big per-bookcase sign above is redundant and skipped. -->
        <Bookshelf
          :node="bookshelf"
          :expand-bookshelf="expandBookshelf"
          :features="features"
          :classification="classification"
          :labels="appSettings.labels"
          :filter="filter"
          :sort="sort"
          :hide-expand="classification.alphabeticalTopNav"
          :transition-direction="transitionDirection"
        />
      </div>
      <!-- Gap --> <div style="width: 70px; height: 1px; flex-shrink: 0" />
    </div>
  </div>
</template>

<script>
import Bookshelf from './Bookshelf.vue';
import GenreTopNav from './GenreTopNav.vue';
import GenreFilterBar from './GenreFilterBar.vue';
import RightArrowIcon from './icons/RightArrowIcon.vue';
import ExpandIcon from './icons/ExpandIcon.vue';
import debounce from 'lodash/debounce';
import { nextTick } from 'vue';
import { decrementStringSolr, hierarchyFind, testLuceneSyntax, pollUntilTruthy } from '../utils.js';
import CONFIGS from '../../configs';
/** @typedef {import('../utils.js').ClassificationNode} ClassificationNode */

/**
 * Given a starting classification node, find the data needed to render the node containing
 * the provided classification string.
 * @param {ClassificationNode} classificationNode
 * @param {string} classification (e.g. 658.91500202854)
 */
function findClassification(classificationNode, classification) {
    // First we find the closest matching node in the current classification tree
    const path = hierarchyFind(
        classificationNode,
        node => testLuceneSyntax(node.hierarchyQuery || node.query, classification));
    if (!path.length) return;

    // pad until length is at least 3, so that we can destructure into [shelf, bookcase, room]
    while (path.length < 3) path.push(null);

    // Jump as deep into it as we can. I.e. the last node is the shelf, the second last the bookcase, and the 3rd last is the room.
    // e.g. [658, 65X, 6XX]
    const [shelf, bookcase, room] = path.reverse();
    path.reverse();
    return {
        classification,
        room,
        bookcase,
        shelf,
        breadcrumbs: path.slice(0, -3),
    };
}

/**
 * Finds a genre or subgenre node by its bare `short` slug -- what a plain #-style URL
 * anchor, or a bare `?jumpTo=subject_key:<slug>`, naturally provides. findClassification/
 * hierarchyFind above expect an already ancestor-prefixed hierarchyQuery-format string
 * (e.g. "horror/vampires") to match a subgenre correctly; a bare slug someone typed or
 * linked to never has that prefix, and genre mode's toQueryFormat is the identity
 * function, so it never adds one either -- without this, a subgenre-level jumpTo/hash
 * silently fails to match anything and falls back to "All Genres". A subgenre with
 * multiple parent genres (e.g. Apocalyptic under Horror/Sci-Fi/Fantasy) resolves to
 * whichever parent it's listed under first; a bare slug has no ancestor context to
 * disambiguate further.
 * @param {ClassificationNode} root
 * @param {string} slug
 */
function findGenreNodeBySlug(root, slug) {
    for (const genre of root.children) {
        if (genre.short === slug) return { classification: slug, bookcase: genre, shelf: null };
        const shelf = genre.children?.find(c => c.short === slug);
        if (shelf) return { classification: slug, bookcase: genre, shelf };
    }
    return null;
}

export default {
    components: {
        Bookshelf,
        GenreTopNav,
        GenreFilterBar,
        RightArrowIcon,
        ExpandIcon,
    },
    props: {
        /** @type {import('../utils.js').ClassificationTree} */
        classification: Object,
        appSettings: Object,

        /** The classification to jump to @example 658.91500202854 */
        jumpTo: String,
        sort: String,
        // Raw, mutable filter/sort state (genre mode's GenreFilterBar mutates these
        // directly, same reference LibraryToolbar.vue already mutates -- `filter`/`sort`
        // above are the derived string/order value used for the actual Solr queries).
        filterState: Object,
        sortState: Object,
        filter: {
            default: '',
            type: String
        },
        features: {
            default: () => ({
                book3d: true,
                cover: 'image',
                shelfLabel: 'slider',
            })
        }
    },
    data() {
        const jumpToData = this.jumpTo && (
            this.classification.alphabeticalTopNav
                ? findGenreNodeBySlug(this.classification.root, this.jumpTo)
                : findClassification(this.classification.root, this.jumpTo)
        );
        // Genre mode has no DDC/LCC-style continuous scroll-through-siblings -- "All Genres"
        // and a specific genre are different views entirely, switched via the top nav, not
        // scroll position. So a genre-level jumpTo drills straight into that genre (matching
        // what clicking it in the top nav does) instead of landing on All Genres with the
        // genre merely scrolled to, which also used to silently never actually scroll on a
        // fresh page load (mounted()'s scrollIntoView only ever triggered on a shelf match).
        const drillIn = this.classification.alphabeticalTopNav && jumpToData?.bookcase;
        const activeRoom = drillIn || jumpToData?.room || this.classification.root;
        const breadcrumbs = drillIn ? [this.classification.root] : (jumpToData?.breadcrumbs || []);

        // Resolve the actual starting index so the URL (kept in sync via the currentNode
        // watcher below) doesn't briefly flash a wrong shelf before the scroll settles.
        const initialShelf = drillIn ? jumpToData?.shelf : (jumpToData?.bookcase || jumpToData?.shelf);
        const activeBookcaseIndex = initialShelf ? Math.max(0, activeRoom.children.indexOf(initialShelf)) : 0;

        return {
            activeRoom,
            breadcrumbs,
            jumpToData,

            expandingAnimation: false,
            // Which direction Bookshelf's cross-slide (genre mode only) enters new
            // content from -- updated just before activeRoom changes in switchActiveRoom.
            transitionDirection: 'right',

            roomWidth: 1,
            viewportWidth: 1,
            activeBookcaseIndex,
        };
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
        },
        // Genre mode: one bookcase, always -- "All Genres" shows one shelf per top-level
        // genre, a specific genre shows one shelf per subgenre.
        bookcases() {
            return this.classification.alphabeticalTopNav ? [this.activeRoom] : this.activeRoom.children;
        },
        // Which top-level genre (if any) is currently drilled into, for GenreTopNav's
        // highlight -- -1 (nothing found) means activeRoom IS classification.root, i.e.
        // "All Genres" is the current selection.
        activeGenreIndex() {
            return this.classification.root.children.indexOf(this.activeRoom);
        },
        // Same alphabetical order GenreTopNav displays -- what "swipe left to reach the
        // bookcase to the right" (selectAdjacentGenre) moves through.
        sortedGenres() {
            return this.classification.alphabeticalTopNav
                ? [...this.classification.root.children].sort((a, b) => a.name.localeCompare(b.name))
                : [];
        },
        // Whatever bookcase is currently centered/active in a DDC/LCC-style continuous
        // scroll-through-siblings -- doesn't apply to genre mode, which has exactly one
        // bookcase on screen at a time (selectGenre/selectAllGenres update the URL directly
        // instead, see below). node.short round-trips through toQueryFormat/testLuceneSyntax
        // the same way a jumpTo query param does, so it's what we mirror into the URL.
        currentNode() {
            return this.activeRoom.children?.[this.activeBookcaseIndex];
        },
    },
    watch: {
        async classification(newVal) {
            this.activeRoom = newVal.root;
            this.breadcrumbs = [];
            await nextTick();
            this.updateWidths();
            this.updateActiveShelfOnScroll();
        },
        currentNode(node) {
            if (!node || this.classification.alphabeticalTopNav) return;
            const url = new URL(location.href);
            url.searchParams.set('jumpTo', `${this.classification.field}:${node.short}`);
            history.replaceState(null, '', url);
        },
    },

    async created() {
        this.debouncedUpdateWidths = debounce(this.updateWidths);
        window.addEventListener('resize', this.debouncedUpdateWidths, { passive: true });
    },
    async mounted() {
        this.updateWidths();
        // #-style anchors (e.g. /explore/genres#fantasy) are genre mode's live-navigable
        // counterpart to ?jumpTo=subject_key:fantasy -- the query-param form only ever
        // resolves once, at initial mount, and changing it implies a fresh page load in
        // this server-rendered shell, but a hash is meant to be updated (and reacted to)
        // without reloading at all, e.g. a homepage genre link the app is already open to.
        if (this.classification.alphabeticalTopNav) {
            window.addEventListener('hashchange', this.onHashChange);
            // Vertical stepping is native CSS scroll-snap now (see the .shelf snap rules in
            // <style>): the browser owns the trackpad momentum, so one gesture = one shelf
            // with zero JS in the vertical path -- which is exactly where every prior
            // wheel-timing heuristic failed. This wheel listener remains only for the
            // separate *horizontal* genre switch; onWindowWheel ignores vertical wheels
            // entirely, never calling preventDefault on them, so native scroll is untouched.
            // Non-passive so the horizontal branch's preventDefault takes effect; attached
            // to window so a gesture anywhere on the page (even the site header above the
            // Explorer) is seen.
            window.addEventListener('wheel', this.onWindowWheel, { passive: false });
        }
        if (this.jumpToData?.shelf) {
            if (this.classification.alphabeticalTopNav) {
                // Native scroll-snap handles alignment: the shelf's own scroll-margin-top
                // keeps it clear of the sticky nav, so a plain scrollIntoView lands it in
                // exactly the same place a manual step would settle.
                await nextTick();
                this.$el.querySelector(`.shelf[data-short="${this.jumpToData.shelf.short}"]`)
                    ?.scrollIntoView({ block: 'start' });
                return;
            }
            this.$el.querySelector(`[data-short="${this.jumpToData.shelf.short}"]`).scrollIntoView({
                inline: 'center',
                block: 'start',
            });

            // Classifications like genre have no `${field}_sort` Solr field (they're backed by the
            // unordered `subject_key` field), so there's no stable ordering to compute a precise
            // book offset from -- landing on the right shelf (above) is as precise as jumpTo gets.
            if (this.classification.supportsPreciseJump === false) return;

            // Find the offset of the predecessor of the requested item in its shelf
            const predecessor = decrementStringSolr(this.jumpToData.classification, false, this.classification.field === 'ddc');
            const shelf_query = `${this.classification.field}_sort:${this.jumpToData.shelf.query} ${this.filter}`;
            /** @type {number} */
            const offset = await fetch(`${CONFIGS.OL_BASE_SEARCH}/search.json?${new URLSearchParams({
                q: `${shelf_query} AND ${this.classification.field}_sort:[* TO ${predecessor}]`,
                limit: 0,
            })}`).then(r => r.json()).then(r => r.numFound);
            const olCarousel = await pollUntilTruthy(
                () => this.$el.querySelector(`.ol-carousel[data-short="${this.jumpToData.shelf.short}"]`),
                { timeout: 5000, interval: 100 }
            );
            const pageOffset = await olCarousel._hack_loadPageContainingOffset(offset + 1);
            const bookEl = await pollUntilTruthy(
                () => olCarousel.querySelector(`.book:nth-of-type(${(offset + 1) - pageOffset})`),
                { timeout: 5000, interval: 100 }
            );

            bookEl.scrollIntoView({
                inline: 'center'
            });
        }
    },
    unmounted() {
        window.removeEventListener('resize', this.debouncedUpdateWidths);
        window.removeEventListener('hashchange', this.onHashChange);
        window.removeEventListener('wheel', this.onWindowWheel);
    },
    methods: {
        // Resolves a #-style anchor the same way jumpTo resolves at mount (findGenreNodeBySlug,
        // above), then navigates client-side -- no page reload, unlike the query-param form.
        // A genre-level hash (e.g. #fantasy) switches straight to it; a subgenre-level hash
        // (e.g. #vampires) drills into its parent genre and scrolls to that specific shelf,
        // matching jumpTo's own drillIn behavior in data() above.
        async onHashChange() {
            const slug = decodeURIComponent(location.hash.slice(1));
            if (!slug) return;
            const found = findGenreNodeBySlug(this.classification.root, slug);
            if (!found) return;
            if (found.bookcase !== this.activeRoom) {
                await this.switchActiveRoom(found.bookcase, [this.classification.root]);
            }
            if (found.shelf) {
                await nextTick();
                this.$el.querySelector(`.shelf[data-short="${found.shelf.short}"]`)
                    ?.scrollIntoView({ block: 'start' });
            }
        },

        async selectAllGenres() {
            await this.switchActiveRoom(this.classification.root, []);
        },

        /** @param {number} index into classification.root.children */
        async selectGenre(index) {
            await this.switchActiveRoom(this.classification.root.children[index], [this.classification.root]);
        },

        // Mirrors the "adjacent bookcase, just out of view" feeling DDC/LCC's continuous
        // scroll gives for free -- since genre mode has exactly one bookcase on screen
        // (no neighbors to actually scroll past), Bookshelf's cross-slide direction is
        // instead driven by alphabetical order (the same order the top nav displays), so
        // clicking a genre that reads later/earlier in that strip slides new content in
        // from the matching side. Entering a genre from All Genres reads as "forward"
        // (right); returning to All Genres reads as "back" (left).
        directionTo(newRoom) {
            const root = this.classification.root;
            if (newRoom === root) return 'left';
            if (this.activeRoom === root) return 'right';
            return newRoom.name.localeCompare(this.activeRoom.name) >= 0 ? 'right' : 'left';
        },

        /**
         * Moves to the next/previous genre in alphabetical order (the same order
         * GenreTopNav displays) -- e.g. swiping to reveal "the bookcase to the right"
         * of Crime moves to Drama. From "All Genres", swiping forward (the same
         * direction that enters a genre in the first place, per directionTo) continues
         * on into the first genre in the list, rather than being a no-op; swiping
         * backward is still a no-op (nothing precedes "All Genres"). Also a no-op past
         * the *other* end of the list.
         * @param {1 | -1} step
         */
        selectAdjacentGenre(step) {
            const sorted = this.sortedGenres;
            if (this.activeRoom === this.classification.root) {
                if (step !== 1 || !sorted.length) return;
                this.selectGenre(this.classification.root.children.indexOf(sorted[0]));
                return;
            }
            const currentIndex = sorted.indexOf(this.activeRoom);
            const nextIndex = currentIndex + step;
            if (currentIndex === -1 || nextIndex < 0 || nextIndex >= sorted.length) return;
            this.selectGenre(this.classification.root.children.indexOf(sorted[nextIndex]));
        },

        // Vertical stepping is native CSS scroll-snap (see the .shelf snap rules in
        // <style>), so this window-level listener now only handles the *horizontal* genre
        // switch. It deliberately ignores vertical wheels -- never calling preventDefault
        // on them -- so the browser's own momentum + scroll-snap-stop is the sole driver
        // of vertical motion.
        //
        // Horizontal gestures switch genres (selectAdjacentGenre), except inside a shelf's
        // own carousel (.shelf-carousel) -- scrolling books there should keep loading more
        // of the *current* shelf, not navigate away from it.
        onWindowWheel(e) {
            if (!this.classification.alphabeticalTopNav) return;

            const absX = Math.abs(e.deltaX);
            const absY = Math.abs(e.deltaY);

            // Vertical is entirely native -- leave it alone.
            if (absX <= absY) return;

            // Only switches genres from "home" or the first shelf -- once you've scrolled
            // further down into the bookcase, a horizontal component is much more likely to
            // be an imprecise trackpad diagonal while scrolling vertically than an intent to
            // switch away entirely, and misfiring there was reported as a real problem.
            if (!this.isNearTop()) return;
            // e.target, not composedPath()[0], would be wrong here: this listener is on
            // window, outside <ol-library-explorer>'s shadow root, so per shadow DOM event
            // retargeting, e.target for anything originating *inside* that shadow tree gets
            // reported as the shadow host itself -- .closest() on that would never find
            // .shelf-carousel regardless of where the gesture actually started.
            // composedPath()[0] is the true originating element, unaffected by retargeting.
            if (e.composedPath()[0]?.closest?.('.shelf-carousel')) return;
            e.preventDefault();
            // One physical swipe = one genre switch, WITHOUT the aggressive delay a fixed
            // time-lock causes: a trackpad's momentum tail keeps streaming events, so a lock
            // long enough to swallow the tail also blocks a genuine quick second swipe. Key
            // insight -- momentum only ever DECAYS (|deltaX| trends down); a new swipe RE-
            // ACCELERATES it. So fire when the gesture is freshly armed (after a quiet gap)
            // OR when deltaX clearly re-accelerates after having decayed, and never on the
            // decaying tail in between. Entirely separate from the vertical snap (different
            // case, no shared state or timing).
            const prev = this._hPrevAbsX || 0;
            if (absX < prev * 0.7) this._hDecayed = true;   // momentum is dying off
            const reaccelerated = this._hDecayed && absX > prev * 1.4 && absX > 12;
            if (this._hArmed !== false || reaccelerated) {
                this._hArmed = false;
                this._hDecayed = false;
                this.selectAdjacentGenre(e.deltaX > 0 ? 1 : -1);
            }
            this._hPrevAbsX = absX;
            // Re-arm (and forget the momentum baseline) once horizontal events go quiet --
            // short, because re-acceleration already catches quick successive swipes.
            clearTimeout(this._hQuietTimer);
            this._hQuietTimer = setTimeout(() => {
                this._hArmed = true; this._hPrevAbsX = 0; this._hDecayed = false;
            }, window.OL_H_QUIET_MS ?? 90);
        },

        // True while the shelves pane is scrolled no further than its first shelf -- the
        // only region a horizontal gesture is allowed to switch genres
        // (onWindowWheel/onShelvesTouchEnd). Read from the pane's own scrollTop, since the
        // pane (not the document) is genre mode's vertical scroller.
        isNearTop() {
            const shelves = this.$el.querySelectorAll('.shelf');
            if (shelves.length < 2) return true;
            // Horizontal genre switch is allowed only at or above the 1st shelf -- i.e. at
            // home or with the 1st shelf snapped -- never once the 2nd shelf is the active
            // one. Gate on the 2nd shelf's SNAP position (its pane offset minus the sticky
            // nav height), not its raw top, so being snapped on shelf 1 correctly disallows
            // it. .book-room is the scroll container.
            const nav = this.$el.querySelector('.genre-top-nav-wrapper')?.offsetHeight || 0;
            const paneTop = this.$el.getBoundingClientRect().top;
            const secondShelfSnap = (shelves[1].getBoundingClientRect().top - paneTop + this.$el.scrollTop) - nav;
            return this.$el.scrollTop < secondShelfSnap - 5;
        },

        onShelvesTouchStart(e) {
            if (!this.classification.alphabeticalTopNav || e.target.closest('.shelf-carousel')) {
                this._touchStart = null;
                return;
            }
            this._touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        },

        onShelvesTouchEnd(e) {
            if (!this._touchStart) return;
            const dx = e.changedTouches[0].clientX - this._touchStart.x;
            const dy = e.changedTouches[0].clientY - this._touchStart.y;
            this._touchStart = null;
            if (Math.abs(dx) < 60 || Math.abs(dx) <= Math.abs(dy)) return;
            // Same restriction as onWindowWheel's horizontal branch: only from "home" or
            // the first shelf.
            if (!this.isNearTop()) return;
            // A left-drag (negative dx) reveals content further right, same as wheel above.
            this.selectAdjacentGenre(dx < 0 ? 1 : -1);
        },

        // Shared by selectAllGenres/selectGenre rather than reusing expandBookshelf's
        // push-onto-existing-breadcrumbs behavior, since jumping directly between two
        // genres via the top nav should reset to a single-level breadcrumb (back to All
        // Genres), not grow a stack the way drilling deeper via "See more" does.
        //
        // Updates the URL directly here rather than via the currentNode watcher: with
        // exactly one (vertically-stacked, not scrolled-through) bookcase on screen at a
        // time, there's no "currently centered shelf" to track the way DDC/LCC's
        // continuous horizontal scroll has -- the selected genre itself is what's
        // shareable. "All Genres" has no specific classification target, so it clears
        // jumpTo rather than pointing at an arbitrary first genre.
        async switchActiveRoom(room, breadcrumbs) {
            this.transitionDirection = this.directionTo(room);
            this.activeRoom = room;
            this.breadcrumbs = breadcrumbs;
            this.activeBookcaseIndex = 0;
            // A fresh genre view always starts at "home" -- the top of the scroll pane
            // (.book-room itself), showing nav + filter + first shelf.
            this.$el.scrollTop = 0;

            const url = new URL(location.href);
            if (room === this.classification.root) {
                url.searchParams.delete('jumpTo');
            } else {
                url.searchParams.set('jumpTo', `${this.classification.field}:${room.short}`);
            }
            history.replaceState(null, '', url);

            await nextTick();
            this.updateWidths();
        },

        /**
         * @param {ClassificationNode} bookshelf something that is currently a bookcase, that will be the new room
         * @param {ClassificationNode} [shelf] the shelf (child of bookshelf)
         */
        async expandBookshelf(bookshelf, shelf=null) {
            this.expandingAnimation = true;
            await new Promise(r => setTimeout(r, 200));
            this.expandingAnimation = false;
            this.breadcrumbs.push(this.activeRoom);
            this.activeRoom = bookshelf;
            const nodeToScrollTo = shelf?.position === 'root' ? shelf :
                shelf?.children && shelf?.position ? shelf.children[shelf.position]
                    : (shelf || bookshelf);
            await nextTick();
            this.$el.querySelector(`[data-short="${nodeToScrollTo.short}"]`).scrollIntoView();
        },

        async goUpTo(index) {
            const nodeToScrollTo = this.activeRoom;
            this.activeRoom = this.breadcrumbs[index];
            this.breadcrumbs.splice(index, this.breadcrumbs.length - index);
            await nextTick();
            this.$el.querySelector(`[data-short="${nodeToScrollTo.short}"]`).scrollIntoView();
        },

        updateWidths() {
            const { max } = Math;
            // Avoid dividing by 0 and whatnot
            this.roomWidth = max(1, this.$el.querySelector('.book-room-shelves').scrollWidth);
            this.viewportWidth = max(1, this.$el.getBoundingClientRect().width);

            if (this.roomWidth === 1 || this.viewportWidth === 1) {
                setTimeout(this.updateWidths, 100);
            }

            // Only .genre-top-nav-wrapper is actually position: sticky -- GenreFilterBar
            // scrolls away with the page like normal content. Set once here (not
            // recomputed per navigation) as a CSS custom property that .shelf's
            // scroll-margin-top reads, below -- so scrollIntoView natively lands each
            // shelf right below the sticky nav, without any manual scrollY/rect math.
            if (this.classification.alphabeticalTopNav) {
                const navHeight = this.$el.querySelector('.genre-top-nav-wrapper')?.offsetHeight || 0;
                this.$el.style.setProperty('--genre-nav-height', `${navHeight}px`);

                // Size the scroll pane (.book-room itself) to fill the viewport below the
                // site header. This pane -- NOT the document -- is genre mode's vertical
                // scroll container, so scroll-snap is confined to the explorer and the
                // document/site header stay normal (the top is always reachable; document-
                // level snapping is what hijacked "scroll to top"). The site header height
                // isn't known to CSS, so measure it here (and on resize) as this.$el's
                // distance from the top of the viewport while the document is unscrolled.
                const top = this.$el.getBoundingClientRect().top + window.scrollY;
                this.$el.style.setProperty('--genre-pane-height', `${Math.max(200, Math.round(window.innerHeight - top))}px`);
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

<style>
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
}
@media (max-width: 450px) {
  .lr-signs {
    top: 75%;
  }
}

.bookshelf-signage--sign {
  background: #232323;
  color: white;
  box-sizing: border-box;
  border-radius: 4px;
  overflow: hidden;
  overflow: clip;
}
.bookshelf-signage--sign .sign-classification {
  opacity: .5;
  font-size: .9em;
}

.bookshelf-signage--lr-sign {
  max-width: 300px;
  margin: 0;
  line-height: 1em;
  padding: 14px;
  pointer-events: all;
  border: 0;
}
.bookshelf-signage--lr-sign:hover {
  background: #303030;
}
.bookshelf-signage--lr-sign.left .sign-body .arrow-icon {
  float: left;
  transform: rotateZ(-180deg);
  margin-right: 8px;
}
.bookshelf-signage--lr-sign.right .sign-body .arrow-icon {
  float: right;
}
@media (min-width: 450px) {
  .bookshelf-signage--lr-sign {
    min-width: 150px;
    width: 25%;
    margin: 4px;
  }
}
@media (max-width: 450px) {
  .bookshelf-signage--lr-sign .sign-label,
  .bookshelf-signage--lr-sign .sign-classification {
    display: none;
  }
  .bookshelf-signage--lr-sign.left .sign-body .arrow-icon {
    margin-right: 0;
  }
}
.bookshelf-signage--lr-sign .sign-toolbar {
  display: none;
}
.bookshelf-signage--lr-sign .sign-label {
  text-overflow: ellipsis;
  overflow: hidden;
  overflow: clip;
  white-space: nowrap;
}
.bookshelf-signage--lr-sign svg {
  padding: .5em .2em;
}

.bookshelf-signage--center-sign {
  display: flex;
  flex-direction: column;
  max-width: 500px;
  min-height: 124px;
  width: 100%;
  padding-top: 20px;
}
@media (min-width: 450px) {
  .bookshelf-signage--center-sign {
    min-width: 400px;
  }
}
.bookshelf-signage--center-sign .sign-body .arrow-icon {
  display: none;
}
.bookshelf-signage--center-sign .sign-body {
  flex: 1;
}
.bookshelf-signage--center-sign .sign-label {
  font-size: 1.3em;
}
.bookshelf-signage--center-sign .sign-toolbar {
  background: #2c2c2c;
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
}
.bookshelf-signage--center-sign .sign-toolbar button {
  font-size: 0.75em;
  opacity: 0.95;
}
.bookshelf-signage--center-sign .sign-toolbar .label {
  margin-left: 3px;
}
.bookshelf-signage--center-sign .sign-toolbar svg {
  height: 14px;
  width: 14px;
  margin-bottom: -2px;
}
.bookshelf-signage--center-sign .sign-classification,
.bookshelf-signage--center-sign .sign-label {
  padding: 0 25px;
}

.bookshelf-signage--breadcrumb-sign {
  transform-origin: bottom center;
  transform: scale(.85);
  opacity: .8;
}
.bookshelf-signage--breadcrumb-sign div {
  display: inline-block;
}
.bookshelf-signage--breadcrumb-sign .sign-label {
  margin-left: 1em;
}

.bookshelf-signage--main-sign {
  padding: 20px 30px;
}
.bookshelf-signage--main-sign .sign-label {
  font-size: 1.3em;
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
}
.bookshelf.bookshelf-back.v-enter,
.bookshelf.bookshelf-back.v-leave-to {
  transform: initial;
  filter: initial;
  opacity: 0;
}

.book-room.genre-mode {
  background: #3a271d;
  /* THE genre-mode scroll container. It holds the whole explorer -- sticky top nav, the
     filter controls, and the shelves -- in ONE scroll region, so the nav stays pinned, the
     controls scroll up and away, and the shelves snap, all as one gesture-driven scroll.
     Height is measured (updateWidths) to fill the viewport below the site header, so this
     pane scrolls rather than the document -- the document/site header stay normal and the
     top is always reachable (document-level snapping is what hijacked "scroll to top").
     overflow-x:hidden clips the genre cross-slide; overscroll-behavior:contain stops the
     gesture chaining to the document or firing the browser back/forward swipe. */
  height: var(--genre-pane-height, 85vh);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-snap-type: y mandatory;
  overscroll-behavior: contain;
}
/* Home is a real snap position at scrollTop 0 (see the .genre-scroll-home sentinel in the
   template for why it's anchored here and not on the sticky nav or late-rendering filter):
   scrolling all the way up rests with nav + filter + first shelf visible, and the first
   scroll-down step snaps past it onto shelf 0. Zero height so it takes no layout space.
   scroll-snap-stop: always makes it a hard stop symmetric with the shelves -- the controls
   behave as the "0th shelf", so a scroll-up gesture off shelf 0 lands firmly on the controls
   instead of being pulled back down by shelf 0's own stop. */
.book-room.genre-mode .genre-scroll-home {
  height: 0;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
/* For vertical scroll-snap to work, the shelves must snap to .book-room (genre mode's
   scroll container). Any ancestor between .shelf and .book-room whose overflow is not
   `visible` is itself a scroll container that instead CAPTURES the shelves' scroll-snap-
   align -- and because none of them actually scroll vertically, the snapping is swallowed
   and vertical reads as plain scrolling. Two such containers exist in this DOM (built for
   DDC/LCC's horizontal scroll): .book-room-shelves (base overflow-x:auto forces overflow-y
   to compute to auto) and .bookshelf (overflow:hidden frame). Neutralize both in genre
   mode -- there's exactly one bookcase here, so neither needs to scroll, and the full-bleed
   frame's cross-slide runs off the viewport edge without needing to be clipped. */
.book-room.genre-mode .book-room-shelves {
  /* Not a scroll container -- the scroller is .book-room (see above), so that the sticky
     nav, the scrolling-away filter bar, and the shelves all live in ONE scroll region.
     display:block instead of the base flex (one bookcase here), and overflow:visible so it
     doesn't capture the shelves' scroll-snap-align (that must belong to .book-room). */
  display: block;
  overflow: visible;
  padding-bottom: 60px;
}
/* The classification "short" code (e.g. DDC's "004") is meaningless for genre/subgenre --
   it's an internal subject_key query slug, not a display code -- so it's hidden here. */
.book-room.genre-mode .classification-short {
  display: none;
}
/* Vertical stepping is native scroll-snap -- no JS in the vertical path, and completely
   independent of the horizontal genre switch (onWindowWheel), which shares no state with
   it. scroll-snap-stop: always is the crux: it forbids a single scroll gesture (including
   a trackpad's momentum tail) from passing more than one shelf, so one flick = one shelf,
   with the *browser* doing the momentum math rather than JS re-deriving gesture boundaries
   from wheel timing (which is what every prior attempt failed at). scroll-snap-type: y
   mandatory lives on the scroll container (.book-room); scroll-margin-top = the sticky nav
   height so each snapped shelf lands just below the nav rather than under it. */
.book-room.genre-mode .shelf {
  scroll-snap-align: start;
  scroll-snap-stop: always;
  scroll-margin-top: var(--genre-nav-height, 0px);
}

/* A softer, more contemporary take on the bookcase/shelf skin for genre mode: layered
   shadows (top highlight, bottom lift) instead of a flat 3px black border, and a richer
   multi-stop walnut gradient instead of a flat black box -- still explicitly a wood
   shelf (skeuomorphic), just less "clip-art". Scoped to .genre-mode so DDC/LCC's
   existing look is untouched.

   Full-bleed rather than a centered 900px card (see .bookshelf-wrapper below) -- one
   continuous shelf spanning the viewport, not a boxed-in card, so there's no left/right
   edge for books to visibly get cut off against. No border-radius here for the same
   reason: rounded corners only make sense where an edge is actually visible (top/bottom). */
.book-room.genre-mode .bookshelf {
  background: linear-gradient(180deg, #4a3222 0%, #3a2718 60%, #2e1e12 100%);
  border: 0;
  border-radius: 0;
  box-shadow:
    0 8px 20px rgba(0, 0, 0, .45),
    inset 0 1px 0 rgba(255, 255, 255, .06);
  /* Base .bookshelf is overflow:hidden, which makes it a scroll container that would
     capture the shelves' scroll-snap-align (see .book-room-shelves note above). Genre
     mode's cross-slide runs off the full-bleed viewport edge, so clipping isn't needed
     here -- drop it so vertical snap belongs to the document. */
  overflow: visible;
}
.book-room.genre-mode .bookshelf-wrapper {
  width: 100%;
  max-width: 100%;
  margin: 0;
  /* The base rule gives this scroll-snap-align: center for DDC/LCC's horizontal bookcase
     snapping. In genre mode it's a stray snap point on an element taller than the viewport
     (it wraps ALL shelves), which fights the real per-shelf/home snap points -- it was why
     the page loaded snapped past the filter onto shelf 0. Genre mode's snapping is on the
     shelves and the filter, never this wrapper. */
  scroll-snap-align: none;
}
/* LibraryExplorer.vue's .book-room.style--aesthetic--wip .bookshelf-wrapper sets its own
   margin-left: 140px at the exact same specificity (3 classes) as the rule above --
   a tie that source order (not intent) decides between the two <style> blocks, and can
   silently flip whenever the Vite bundle's chunk order shifts. Naming both classes here
   raises this rule's specificity above that tie so genre mode's full-bleed layout always
   wins regardless of bundle order. */
.book-room.style--aesthetic--wip.genre-mode .bookshelf-wrapper {
  margin-left: 0;
}
/* Skeuomorphic shelf ledge (genre mode). Books rest on a real wooden plank: a lit top
   surface, a darker front lip for thickness, a soft drop shadow so the shelf reads as
   floating, and a contact shadow that grounds the books on it. Modern-but-real -- warm
   wood + soft diffuse shadows, not flat cartoon planks. --shelf-plank-h reserves the space
   the plank occupies (via padding-bottom) so book bottoms sit ON its surface, not over it. */
.book-room.genre-mode .shelf-carousel {
  --shelf-plank-h: 36px;
  position: relative;
  border: 0;
  border-radius: 0;
  padding-bottom: var(--shelf-plank-h);
  /* the wall behind the books: warm wood, darkening toward the shelf */
  background:
    linear-gradient(180deg, rgba(0, 0, 0, .32) 0%, transparent 56px),
    linear-gradient(180deg, #5c4029 0%, #4a3220 100%);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, .4);
}
/* contact shadow -- darkens the wall just above the plank so books look planted */
.book-room.genre-mode .shelf-carousel::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: var(--shelf-plank-h);
  height: 22px;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, .42));
  pointer-events: none;
  z-index: 0;
}
/* the plank itself: lit top face over a darker front lip (the seam at ~62% fakes the
   board's thickness), plus a diffuse drop shadow beneath for the floating-shelf look */
.book-room.genre-mode .shelf-carousel::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: var(--shelf-plank-h);
  /* top ~15px = the lit board surface books stand on; then a thin seam; then the darker
     front lip (thickness). Reads as looking slightly down onto a real shelf board. */
  background: linear-gradient(180deg,
    #9a734d 0%,            /* bright leading highlight */
    #825c3a 5%,            /* board top surface */
    #6d4c30 40%,
    #573c26 43%,           /* surface -> lip seam (shadow) */
    #4a3320 46%,           /* front lip (thickness) */
    #2c1d11 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, .16),   /* crisp lit front-top edge */
    0 14px 22px -8px rgba(0, 0, 0, .6);        /* floating shadow under the shelf */
  pointer-events: none;
  z-index: 1;
}
.book-room.genre-mode .shelf-label {
  border-radius: 6px;
  background: linear-gradient(180deg, #2a2a2a, #1c1c1c);
}
</style>
