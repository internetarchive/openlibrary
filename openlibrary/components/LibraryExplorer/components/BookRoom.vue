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
    <div
      v-if="classification.alphabeticalTopNav"
      ref="stickyHeader"
      class="genre-sticky-header"
    >
      <GenreTopNav
        :nodes="classification.root.children"
        :active-index="activeGenreIndex"
        @select="selectGenre"
        @select-all="selectAllGenres"
      />
      <GenreFilterBar
        :filter-state="filterState"
        :sort-state="sortState"
        :genre-enriched="genreEnriched"
        :chips-teleport-target="stickyHeaderEl"
        :initial-language-keys="initialLanguageKeys"
        @update:genre-enriched="$emit('update:genre-enriched', $event)"
        @ready="updateWidths"
      />
      <!-- The bookcase's own top board -- a wood-plank frame mirroring the shelves' own
           baseboard, so the case reads as one continuous carcass topped and bottomed the
           same way, rather than shelves just starting abruptly under the nav. -->
      <div
        class="genre-top-board"
        aria-hidden="true"
      />
    </div>
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
        // Genre mode's basic/enriched tree toggle -- see LibraryExplorer.vue's genreEnriched
        // watcher, which is what actually swaps `classification.root` when this changes.
        genreEnriched: Boolean,
        // Pass-through to GenreFilterBar -- see its own prop doc for why language is the
        // one URL-shareable filter LibraryExplorer.vue can't just apply to filterState itself.
        initialLanguageKeys: {
            type: Array,
            default: () => [],
        },
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

            // Set in mounted() once $refs.stickyHeader actually exists -- a plain
            // template ref isn't reactive on its own, so GenreFilterBar's
            // chips-teleport-target prop (below) wouldn't update once it's assigned.
            stickyHeaderEl: null,

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
            // Genre mode's basic/enriched toggle lands here (a new root swapped into this
            // prop) -- the old scroll position may no longer correspond to anything
            // sensible in the new tree (different genre count/order), so start over at the
            // top rather than leaving the pane wherever it happened to be scrolled to.
            if (newVal.alphabeticalTopNav) this.$el.scrollTop = 0;
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
            this.stickyHeaderEl = this.$refs.stickyHeader;

            // The site header only auto-hides on window scroll (header-scroll.js, wired up
            // in index.js) -- genre mode's own pane (.book-room, this component's root) is
            // its own scroll container, so window.scrollY never changes here and that
            // listener never fires. Drive the same behavior from this pane's scroll instead.
            const siteHeader = document.getElementById('site-header-autohide');
            if (siteHeader) {
                import(/* webpackChunkName: "header-scroll" */ '../../../plugins/openlibrary/js/header-scroll.js')
                    .then(module => {
                        this._teardownHeaderAutoHide = module.initHeaderAutoHide(siteHeader, this.$el, hidden => {
                            this.$el.classList.toggle('header-collapsed', hidden);
                        });
                    });
            }

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
            // Opt the whole document out of the browser's macOS horizontal swipe-navigation
            // gesture (two-finger swipe = Back/Forward) while genre mode is mounted. That
            // gesture is a lower-level recognizer tied to horizontal overscroll, NOT the
            // wheel event, so onWindowWheel's preventDefault can't stop it -- which is why a
            // right-swipe (= Back, with history) felt "broken"/draggy while a left-swipe
            // (= Forward, no history) felt clean. overscroll-behavior-x on the root scroller
            // is the only thing that disables it. Set inline (not in this shadow-root
            // stylesheet, which can't reach <html>); cleared in unmounted.
            document.documentElement.style.overscrollBehaviorX = 'none';
            // Mark each cover 'is-loaded' once its image finishes, so the skeleton shimmer
            // can be dropped from it. Capture phase because `load` doesn't bubble; needed
            // because covers are object-fit:contain (letterboxed) and the shimmer is the
            // image's own background, so CSS alone can't tell loaded from loading.
            this.$el.addEventListener('load', this.onCoverLoaded, true);
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
        document.documentElement.style.overscrollBehaviorX = '';
        this.$el.removeEventListener('load', this.onCoverLoaded, true);
        this._teardownHeaderAutoHide?.();
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
            //
            // Scanning the full composedPath() (not just .closest() from composedPath()[0])
            // matters specifically for .genre-sticky-header: its controls (ol-toggle,
            // ol-select-popover, ol-options-popover, ol-chip...) are the site-wide Lit
            // bundle's own custom elements, each with its OWN shadow root nested inside
            // <ol-library-explorer>'s -- a gesture starting on, say, the button inside
            // ol-toggle's shadow root can't .closest() out past ol-toggle's own shadow
            // boundary to find an ancestor class in a *different* shadow tree. composedPath()
            // still lists every element the event crosses through, shadow boundaries
            // included, so checking membership in the whole array works regardless of how
            // many shadow roots are nested between the gesture and .genre-sticky-header.
            const path = e.composedPath();
            if (path.some(el => el.classList?.contains('shelf-carousel') || el.classList?.contains('genre-sticky-header'))) return;
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
            if (absX < prev * 0.75) this._hDecayed = true;   // momentum is dying off
            const reaccelerated = this._hDecayed && absX > prev * 1.25 && absX > 8;
            if (this._hArmed !== false || reaccelerated) {
                this._hArmed = false;
                this._hDecayed = false;
                this.selectAdjacentGenre(e.deltaX > 0 ? 1 : -1);
            }
            this._hPrevAbsX = absX;
            // Re-arm (and forget the momentum baseline) once horizontal events go quiet --
            // short, because re-acceleration already catches quick successive swipes. Lower
            // = snappier successive swipes. Live-tunable: window.OL_H_QUIET_MS = 60.
            clearTimeout(this._hQuietTimer);
            this._hQuietTimer = setTimeout(() => {
                this._hArmed = true; this._hPrevAbsX = 0; this._hDecayed = false;
            }, window.OL_H_QUIET_MS ?? 65);
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

        onCoverLoaded(e) {
            const t = e.target;
            if (t && t.tagName === 'IMG' && t.classList && t.classList.contains('cover')) {
                t.classList.add('is-loaded');
            }
        },

        onShelvesTouchStart(e) {
            // Bound directly on .book-room (inside <ol-library-explorer>'s own shadow
            // root, same as .genre-sticky-header), so unlike onWindowWheel above, a touch
            // starting inside a Lit control (ol-toggle etc.) only crosses ONE shadow
            // boundary before reaching this listener -- e.target retargets to that
            // control's own host tag (e.g. <ol-toggle>), which .closest() can still find
            // .genre-sticky-header from, no composedPath() scan needed.
            if (!this.classification.alphabeticalTopNav || e.target.closest('.shelf-carousel, .genre-sticky-header')) {
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

            // .genre-sticky-header (nav + filter bar + top board) is the sticky unit as a
            // whole. Set once here (not recomputed per navigation) as a CSS custom property
            // that .shelf's scroll-margin-top reads, below -- so scrollIntoView natively
            // lands each shelf right below the sticky header, without any manual scrollY/
            // rect math.
            if (this.classification.alphabeticalTopNav) {
                const navHeight = this.$el.querySelector('.genre-sticky-header')?.offsetHeight || 0;
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
                // Same distance, reused when the site header auto-hides (header-scroll.js's
                // onToggle, in mounted() below): this pane doesn't scroll the document, so
                // hiding the header via transform (see header-bar.css) leaves a dead gap
                // above the pane instead of content reclaiming that space the way it does
                // on a normal page. .header-collapsed shifts the pane up by exactly this
                // much and grows it to match, so it fills the gap instead of leaving one.
                this.$el.style.setProperty('--site-header-reclaim-height', `${Math.round(top)}px`);
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

/* Seal the room's internal layering (books, shelves, signs) off from the
   page. The toolbar outside still paints above everything in the room —
   the whole isolated room sits at `auto` beneath its `fixed`. */
.book-room {
  isolation: isolate;
}

.lr-signs {
  position: sticky;
  top: 10px;
  pointer-events: none;
  /* Above the shelves and books (local-1) inside the isolated room. */
  z-index: var(--z-index-local-2);
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
  /* Modern, elegant bookcase: a warm off-white "wall", clean matte wooden shelf boards that
     float on soft warm shadows, and books grounded with gentle contact shadows. Warm-wood
     palette kept in variables so the whole case stays cohesive. */
  /* Warm honey-oak bookcase palette (à la a modern wood bookshop) + slate chalkboard for
     the section signs. */
  --wall: #b28d57;         /* oak back panel of the case */
  --wall-lo: #93713f;      /* recessed/shadowed oak */
  --wood-top: #d2ac74;     /* lit shelf-board surface (faces the light) */
  --wood-face: #b28a55;    /* shelf-board front edge */
  --wood-deep: #7f5f37;    /* shelf-board base / grain shadow */
  --wood-frame: #6f5231;   /* dark oak frame around the chalkboard signs */
  --chalk-board: #2b2a26;  /* slate */
  --chalk-ink: #f0ebde;    /* chalk */
  --shelf-cast: rgba(40, 24, 6, .42);    /* warm shadow the board/sign casts */
  --book-cast: rgba(30, 18, 4, .42);     /* contact shadow under each book */
  --oak-grain: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20width%3D%27500%27%20height%3D%27120%27%3E%3Cfilter%20id%3D%27g%27%3E%3CfeTurbulence%20type%3D%27fractalNoise%27%20baseFrequency%3D%270.003%200.09%27%20numOctaves%3D%274%27%20seed%3D%279%27%2F%3E%3CfeColorMatrix%20type%3D%27matrix%27%20values%3D%270%200%200%200%200%20%200%200%200%200%200%20%200%200%200%200%200%20%200%200%200%200.16%200%27%2F%3E%3C%2Ffilter%3E%3Crect%20width%3D%27500%27%20height%3D%27120%27%20filter%3D%27url%28%23g%29%27%2F%3E%3C%2Fsvg%3E");
  background: var(--wall);
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
  transition: height .25s ease-out, margin-top .25s ease-out;
}
/* The site header hides via transform (see header-bar.css), which never reclaims its own
   layout space -- invisible on a normal page (already scrolled past by the time it hides),
   but this pane doesn't scroll the document at all, so without this it'd leave a dead gap
   above the pane where the header used to be instead of the pane growing into it. Shift up
   by exactly the header's own height (--site-header-reclaim-height, measured in
   updateWidths) and grow by the same amount so the pane's bottom edge stays put. */
.book-room.genre-mode.header-collapsed {
  height: calc(var(--genre-pane-height, 85vh) + var(--site-header-reclaim-height, 0px));
  margin-top: calc(-1 * var(--site-header-reclaim-height, 0px));
}
/* LibraryExplorer.vue's .book-room.style--aesthetic--wip sets a warm tan gradient at the
   same specificity (2 classes) as .book-room.genre-mode, so on a source-order tie it can
   win and muddy the wall. Naming both classes here (3 classes) makes the clean cream wall
   authoritative regardless of bundle order. */
.book-room.style--aesthetic--wip.genre-mode {
  /* The "room" the bookcase sits in -- a soft neutral, deliberately NOT wood: the wood is
     the background of each shelf (which scrolls with its books), so it never reads as a
     static, tiled wallpaper. Controls that scroll over this sit on the neutral, not the
     wood. */
  background: #e9e0cf;
}
/* The sticky unit as a whole -- top nav, filter "sign", and the bookcase's own top board
   (all below) -- so the controls are always visible instead of scrolling away with the
   page. Opaque (matches the room wall) so shelves scrolling underneath never show through
   any gap between the nav and the sign below it. */
.book-room.genre-mode .genre-sticky-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #6c614e;
}
/* GenreFilterBar restyled as a small hanging sign: centered, sized to its own content
   (not a full-width bar), hanging by two thin strings from the dark nav above -- like a
   little placard tacked up in a shop window, rather than a form spanning the room. */
.book-room.genre-mode .genre-filter-bar {
  position: relative;
  width: fit-content;
  max-width: min(90vw, 900px);
  margin: 15px auto 25px auto;
  padding: 10px 18px;
  background: #f3ead4;
  border: 1px solid rgba(0, 0, 0, .25);
  border-radius: 4px;
  box-shadow: 0 6px 14px -6px rgba(0, 0, 0, .45);
}
/* On a narrow viewport the controls don't fit their max-width (90vw here) on one line --
   the base rule's flex-wrap: wrap would spill them onto a second/third row, growing the
   sign tall and pushing the bookcase down. Scroll horizontally within the sign's own width
   instead: one line, same sign height regardless of viewport. justify-content: flex-start
   (not the base rule's center) because centering overflowing flex content is a known trap
   -- browsers can leave the start of the row unreachable by scroll. */
@media (max-width: 767px) {
  .book-room.genre-mode .genre-filter-bar {
    flex-wrap: nowrap;
    overflow-x: auto;
    justify-content: flex-start;
    -webkit-overflow-scrolling: touch;
  }
}
.book-room.genre-mode .genre-filter-bar::before,
.book-room.genre-mode .genre-filter-bar::after {
  content: "";
  position: absolute;
  top: -18px;
  width: 2px;
  height: 18px;
  background: linear-gradient(to bottom, transparent, #8a7355 35%);
}
.book-room.genre-mode .genre-filter-bar::before { left: 30%; }
.book-room.genre-mode .genre-filter-bar::after { left: 70%; }
/* Selected-filter pills float just above the top board (see .genre-top-board) rather than
   adding their own row inside the sign -- like a little placard resting on the shelf's own
   edge, so picking a filter never grows .genre-sticky-header's height. Teleported (see
   GenreFilterBar.vue) to be a direct child of .genre-sticky-header, so this positions
   relative to that, not .genre-filter-bar -- out-specifies GenreFilterBar's own scoped
   .genre-filter-bar__chips (flex-basis: 100%, an in-flow row), which is what that rule is
   for everywhere it isn't overridden -- there is nowhere else it's used, since
   GenreFilterBar only ever renders in genre mode. */
.book-room.genre-mode .genre-filter-bar__chips {
  position: absolute;
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  flex-basis: auto;
  width: max-content;
  max-width: 90vw;
  margin-top: 0;
}
/* Sits the pill on the board the same way the board's own lighting reads: the board's
   gradient (--wood-top lit at the top, darkening toward --wood-deep) implies an overhead
   light, so the pill's own shadow falls straight down beneath it, not off to a side like
   the books' upper-left key light -- a diagonal offset here just looked like a mismatched
   light source. Tight and dark near the pill, short falloff -- a crisp contact shadow, not
   a soft blurred halo. box-shadow/border-radius work on ol-chip's own host box from
   outside its shadow root (unlike its internal .chip fill/border, which are shadow-
   encapsulated) -- the host has no border-radius of its own by default, so it's set here
   to match the pill shape, otherwise the shadow would render as a rectangle behind a
   rounded pill. */
.book-room.genre-mode .genre-filter-bar__chips ol-chip {
  border-radius: 999px;
  box-shadow:
    0 1px 1px rgba(0, 0, 0, .4),
    0 3px 4px -1px rgba(0, 0, 0, .45);
}
/* The bookcase's own top board -- the same wood-plank treatment as each shelf's baseboard
   (see .shelf-carousel::after below), so the case reads as one continuous carcass topped
   and bottomed the same way instead of shelves just starting abruptly under the nav. */
.book-room.genre-mode .genre-top-board {
  height: 20px;
  background:
    var(--oak-grain),
    linear-gradient(180deg,
      var(--wood-top) 0%,
      var(--wood-top) 8px,
      var(--wood-face) 9px,
      var(--wood-deep) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 247, 231, .5),
    inset 0 -2px 4px rgba(0, 0, 0, .3),
    0 6px 10px -4px var(--shelf-cast);
}
/* Home is a real snap position at scrollTop 0 (see the .genre-scroll-home sentinel in the
   template for why it's anchored here and not on the sticky nav, whose scroll-snap-align
   position tracks wherever it's currently stuck): scrolling all the way up rests with the
   sticky header (nav + filter sign + top board) and the first shelf visible, and the first
   scroll-down step snaps past it onto shelf 0. Zero height so it takes no layout space.
   scroll-snap-stop: always makes it a hard stop symmetric with the shelves -- the header
   behaves as the "0th shelf", so a scroll-up gesture off shelf 0 lands firmly on it instead
   of being pulled back down by shelf 0's own stop. */
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
     header (nav + filter sign + top board) and the shelves all live in ONE scroll region.
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
/* Wood is the background of the SHELF itself, so it scrolls with the books rather than
   being a static, tiled page backdrop. Sized to cover so the grain never visibly tiles
   within a shelf. margin-bottom 0 (4-class selector beats the wip aesthetic's 35px) so the
   shelves stack tight like a real case. */
.book-room.style--aesthetic--wip.genre-mode .shelf {
  position: relative;
  margin-bottom: 0;
  background-color: var(--wall);
  background-image:
    var(--oak-grain),
    radial-gradient(130% 60% at 50% 0%, rgba(255, 238, 205, .16), transparent 55%),
    linear-gradient(180deg, rgba(22, 12, 3, .34) 0, transparent 30px);
  background-size: cover, cover, 100% 100%;
  background-repeat: no-repeat;
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
.book-room.style--aesthetic--wip.genre-mode .bookshelf {
  background: transparent;   /* the warm wall (.book-room) shows through; 4-class selector
                                out-specifies the wip aesthetic's own .bookshelf wood skin */
  border: 0;
  border-radius: 0;
  box-shadow: none;
  /* Base .bookshelf is overflow:hidden, which makes it a scroll container that would
     capture the shelves' scroll-snap-align (see .book-room-shelves note above). Genre
     mode's cross-slide runs off the full-bleed viewport edge, so clipping isn't needed
     here -- drop it so vertical snap belongs to the document. */
  overflow: visible;
  /* The base rule's 36px top padding made room for DDC/LCC's own big per-bookcase sign,
     which genre mode never renders (one bookcase, selected via the top nav instead) --
     now that the sticky header ends in its own top board, that padding just left a dead
     gap between it and the first shelf. */
  padding: 0;
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
.book-room.style--aesthetic--wip.genre-mode .shelf-carousel {
  --shelf-plank-h: 31px;
  position: relative;
  border: 0;
  border-radius: 0;
  /* Shelf.vue's base height (285px) leaves a lot of dead air above the covers -- 4-class
     selector out-specifies it for genre mode only (DDC/LCC keeps 285px). No padding-top
     (removed in favor of a taller height): the extra room above the covers was dead air,
     not something worth reserving via padding. */
  height: 280px;
  /* transparent so the oak wall shows through; 4-class selector out-specifies the wip
     aesthetic's own brown .shelf-carousel skin. The inset top shadow is the underside of
     the shelf above, seating each row inside the case (depth). */
  background: transparent;
  /* Less than --shelf-plank-h (the board's own height, used below) on purpose: the books'
     flex row is sized to this padding-bottom, so shrinking it by --shelf-sink lets books
     extend that far down into the board's own box instead of stopping at its back edge.
     Only the board's lit top surface (its top ~10px) gets covered; its front face stays
     visible below every book, which is what actually reads as resting ON the board rather
     than floating just above it with the whole board exposed underneath. */
  --shelf-sink: 5px;
  padding-bottom: calc(var(--shelf-plank-h) - var(--shelf-sink));
  box-shadow: inset 0 17px 17px -16px rgba(18, 10, 2, .6);
}
/* soft contact shadow the books pool onto the board -- grounds the row */
.book-room.genre-mode .shelf-carousel::before {
  content: "";
  position: absolute;
  left: 4%;
  right: 4%;
  bottom: calc(var(--shelf-plank-h) - 5px);
  height: 16px;
  background: radial-gradient(70% 100% at 50% 100%, rgba(60, 40, 16, .26), transparent 78%);
  pointer-events: none;
  z-index: 0;
}
/* The shelf board: a thick, grained wooden plank. Reads as looking slightly down onto it --
   a bright lit front-top lip, a top surface receding into shadow at the back seam, then the
   tall front face (its thickness), all wrapped in wood grain and a faint varnish sheen. A
   broad soft shadow beneath makes it float above the shelf below. */
.book-room.genre-mode .shelf-carousel::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: var(--shelf-plank-h);
  background:
    var(--oak-grain),
    linear-gradient(180deg,
      var(--wood-top) 0%,
      var(--wood-top) 10px,       /* top surface (catches the light) */
      var(--wood-face) 11px,      /* front edge */
      var(--wood-deep) 100%);
  border-radius: 1px;
  box-shadow:
    inset 0 1px 0 rgba(255, 247, 231, .5),          /* fine lit top edge */
    inset 0 -2px 4px rgba(0, 0, 0, .3),             /* front-face base darkens */
    0 4px 7px -3px var(--shelf-cast),                /* crisp near shadow */
    0 16px 26px -12px var(--shelf-cast);             /* soft floating shadow */
  pointer-events: none;
  z-index: 1;
}
/* A single light source cast across the WHOLE shelf, no WebGL/canvas needed -- a soft warm
   glow from the upper-left easing into a faint dark falloff at the lower-right, layered
   over the carousel with a blend mode so it modulates the books' existing colors rather
   than sitting on top as a flat tint. Every shelf gets the identical gradient, which is
   what makes it read as one consistent room light rather than each book's own tiny sheen
   (below) looking disconnected from its neighbours. z-index 2: above the carousel (which
   has no explicit z-index of its own) but below the baseboard label (z-index 3), so the
   label stays perfectly crisp instead of getting tinted too. */
.book-room.style--aesthetic--wip.genre-mode .shelf::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background:
    radial-gradient(65% 60% at 12% 8%, rgba(255, 248, 224, .35), transparent 60%),
    linear-gradient(135deg, rgba(255, 255, 255, .08) 0%, transparent 45%, rgba(20, 12, 4, .16) 100%);
  mix-blend-mode: soft-light;
}
/* Give each flat cover a step toward a real, photographed book -- subtle, never comical:
   a soft studio-light sheen, a thin page fore-edge for thickness, and a layered realistic
   shadow so it reads as an object sitting proud of the shelf, not a sticker. */
.book-room.genre-mode .book .cover,
.book-room.genre-mode .book > img {
  border-radius: 2px;
  box-shadow:
    0 1px 1px #0000004d,          /* tight contact edge */
    0 7px 12px -5px var(--book-cast),      /* soft ambient */
    8px 2px 10px 2px #00000047;   /* light from upper-left -> shadow lower-right */
}
/* soft directional sheen across the cover (studio light from the upper-left) */
.book-room.genre-mode .book::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  border-radius: inherit;
  background: linear-gradient(108deg,
    rgba(255, 255, 255, .16) 0%,
    rgba(255, 255, 255, .04) 16%,
    transparent 34%,
    transparent 90%,
    rgba(0, 0, 0, .1) 100%);
}
/* a thin block of page edges on the right, giving the book real thickness */
.book-room.genre-mode .book::after {
  content: "";
  position: absolute;
  top: 2px;
  bottom: 1px;
  right: -3px;
  width: 4px;
  z-index: 1;
  border-radius: 0 2px 2px 0;
  background: repeating-linear-gradient(90deg, rgba(120, 100, 70, .55) 0 .5px, #efe6d2 .5px 1.6px);
  box-shadow: 1px 2px 4px -1px rgba(0, 0, 0, .4);
}
/* The subgenre name is DELETED from above the shelf and affixed to the front of the wooden
   baseboard -- a small printed shelf-edge label, like a real bookstore. It's absolutely
   positioned onto the board area (it can't literally live in the ::after pseudo, which
   can't hold dynamic text), which also removes the empty label space that used to sit above
   each shelf. */
.book-room.style--aesthetic--wip.genre-mode .class-slider.shelf-label {
  position: absolute;
  left: 20px;
  bottom: 3px;
  z-index: 3;
  margin: 0;
  padding: 0;
  background: transparent;
  border-radius: 0;
  display: block;
}
.book-room.style--aesthetic--wip.genre-mode .class-slider.shelf-label main {
  text-align: left;
  /* ClassSlider's own base CSS makes <main> position: relative at this viewport width, which
     would make it (rather than .class-slider) the containing block for .label below --
     .sections (the progress-bar track this would otherwise matter for) is already
     display: none in genre mode, so there's nothing left that depends on main being
     positioned here. */
  position: static;
}
.book-room.style--aesthetic--wip.genre-mode .class-slider.shelf-label .label {
  /* Pinned directly to the bottom of .class-slider (itself position: relative from its own
     base rule) instead of relying on where normal block flow happens to leave it after
     .lr-buttons. .lr-buttons collapses to 0 height whenever a shelf has no prev/next
     section arrows (leaf subgenres, drilled into a specific genre) -- with the label
     positioned by flow, that shorter .lr-buttons pulled the whole label up with it,
     floating well above the baseboard instead of sitting on it. Anchoring here instead
     means the tag's position no longer depends on how tall its sibling happens to be. */
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  display: inline-block;
  font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: .72em;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: #2e2109;
  background: #f3ead4;
  padding: 3px 10px;
  border-radius: 2px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .4);
  white-space: nowrap;
}
/* The book carousels scroll horizontally; without this, a leftward trackpad swipe that
   overscrolls one triggers the browser's own back/forward swipe-navigation gesture -- the
   "whole page slides with me" bug. preventDefault on the wheel event can't stop that
   lower-level gesture; opting the horizontal axis out of overscroll (none) is what does. */
.book-room.genre-mode .books-carousel {
  overscroll-behavior-x: none;
  /* Sits above the shelf-board pseudo-elements (z-index 0/1 on .shelf-carousel) -- without
     this, the --shelf-sink overlap (books extending down into the board's own box, above)
     rendered backwards: the board painted OVER the bottom of every cover instead of the
     cover sitting in front of it. */
  position: relative;
  z-index: 2;
}
/* Match the shelf-carousel height override above so a loading shelf's skeleton doesn't
   reserve 285px and then jump to 280px once results arrive. */
.book-room.genre-mode .ol-carousel-skeleton {
  height: 280px;
}

/* ---- coherence pass ---- */

/* Seat books ON the board: the base .book has margin-bottom:10px which floated them ~10px
   above the shelf surface. A skeleton shimmer fills each cover slot while its image loads
   (the opaque cover paints over it once ready), so shelves populate gracefully instead of
   showing blank boxes with an orphaned rating badge. */
@keyframes ol-cover-skeleton {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
/* 4-class selector out-specifies Shelf.vue's `.shelf >>> .book { margin-bottom: 10px }`
   (which ties a 3-class rule and won on source order, keeping the books floating). */
.book-room.genre-mode .books-carousel .book {
  margin-bottom: 0;
  border-radius: 2px;
  /* Drop BooksCarousel's `min-height: 90%`: it makes the .book box ~90% of the carousel
     height regardless of the (usually shorter) loaded cover, leaving empty space above the
     image. The hover transform then scales/lifts that oversized box from its bottom and
     reads as broken. min-height:0 makes the box hug the actual cover so the lift is true. */
  min-height: 0;
  transition: transform .18s ease, box-shadow .18s ease;
  transform-origin: bottom center;
  /* A few books leaning back off true vertical, like a real shelf where not every spine
     stands perfectly straight -- pivoted from the bottom (transform-origin above) so it
     reads as leaning back against the shelf behind it, not tipping sideways into its
     neighbour. perspective() gives rotateX() actual depth to tilt into, rather than just
     flattening the cover vertically. --book-tilt is set per nth-child below; most books
     get 0deg so the effect stays a light accent, not a gimmick. */
  transform: perspective(600px) rotateX(var(--book-tilt, 0deg));
}
.book-room.genre-mode .books-carousel .book:nth-child(7n+2) { --book-tilt: 6deg; }
.book-room.genre-mode .books-carousel .book:nth-child(7n+5) { --book-tilt: 4deg; }
/* Hover: lift the cover off the shelf -- rise a few px and scale up a touch, come in FRONT
   of its neighbours and the baseboard label (z-index). Feels like picking it up, and lifts
   it clear of anything occluding it. */
.book-room.genre-mode .books-carousel .book:hover {
  transform: perspective(600px) rotateX(var(--book-tilt, 0deg)) translateY(-5px) scale(1.04);
  z-index: 5;
}
.book-room.genre-mode .book:hover .cover,
.book-room.genre-mode .book:hover > img {
  /* Bigger, softer, and lower than the resting shadow (below) -- reads as the book casting
     a shadow further down onto the shelf as it lifts away from it. No colored glow (that
     read as a yellow/white blur, not a shadow). */
  box-shadow: 0 26px 34px -10px rgba(0, 0, 0, .6);
}
/* Per-cover skeleton shimmer, removed the instant the image loads. It can't live only on
   the image's background: covers are object-fit:contain (letterboxed), so the background
   shows in the letterbox bars even after the picture loads. Instead JS adds `is-loaded` on
   the image's load event (onCoverLoaded) and the shimmer targets `:not(.is-loaded)` only. */
.book-room.genre-mode .book .cover:not(.is-loaded),
.book-room.genre-mode .book > img:not(.is-loaded) {
  background-image: linear-gradient(100deg, #c1a06f 26%, #dcc199 46%, #c1a06f 66%);
  background-size: 220% 100%;
  animation: ol-cover-skeleton 1.5s ease-in-out infinite;
}

/* Hide the vestigial DDC section-scrub track -- the thin translucent-white bar that read as
   a stray line above each shelf. */
.book-room.genre-mode .shelf-label .sections {
  display: none;
}

/* The subgenre index list's base color:inherit picks up ShelfLabel.vue's dark-bookcase
   white text (correct for DDC/LCC), which is unreadable against genre mode's light wood
   wall. Force a dark ink here to match the baseboard label's own text color. */
.book-room.genre-mode .shelf-index a {
  color: #2e2109;
}

/* Soft, on-theme loading/error indicator instead of the harsh black pill. */
.book-room.genre-mode .status-text {
  background: rgba(58, 38, 18, .82);
  color: #f6ecda;
  border-radius: 0 0 999px 999px;
  padding: 4px 16px;
  font-size: .82em;
  letter-spacing: .02em;
  box-shadow: 0 3px 8px -2px rgba(0, 0, 0, .4);
}
</style>
