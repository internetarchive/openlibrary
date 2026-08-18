<template>
  <section
    class="testing-env"
    :aria-busy="busy ? 'true' : 'false'"
  >
    <template v-if="view === 'loading'">
      <div class="testing-env__main">
        <p
          class="testing-env__blank"
          role="status"
          aria-live="polite"
        >
          {{ strings.loading }}
        </p>
      </div>
    </template>

    <template v-else-if="view === 'error'">
      <div class="testing-env__main">
        <div
          class="testing-env__blank"
          role="alert"
        >
          <p>{{ strings.loadError }}</p>
          <button
            type="button"
            class="testing-env__btn testing-env__btn--small"
            :disabled="busy"
            @click="retry"
          >
            {{ strings.retry }}
          </button>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="testing-env__main">
        <header class="testing-env__bar">
          <h2 class="testing-env__title">
            {{ strings.title }}
          </h2>
          <form
            v-if="isMaintainer"
            method="post"
            class="testing-env__add"
            data-add-form
            @submit.prevent="addPrs"
          >
            <label
              class="shift"
              for="testing-env-add"
            >{{ strings.addPrs }}</label>
            <input
              id="testing-env-add"
              v-model="addInput"
              type="text"
              name="pr"
              class="testing-env__input"
              autocomplete="off"
              :placeholder="strings.addPlaceholder"
            >
            <button
              type="submit"
              class="testing-env__btn testing-env__btn--primary"
              :disabled="busy"
            >
              {{ strings.add }}
            </button>
          </form>
        </header>

        <div
          v-if="prs.length"
          class="testing-env__table-wrap"
        >
          <table class="testing-env__table">
            <thead>
              <tr>
                <th
                  v-if="isMaintainer"
                  scope="col"
                >
                  {{ strings.next }}
                </th>
                <th scope="col">
                  {{ strings.pr }}
                </th>
                <th scope="col">
                  {{ strings.author }}
                </th>
                <th scope="col">
                  {{ strings.assignee }}
                </th>
                <th scope="col">
                  {{ strings.drift }}
                </th>
                <th
                  v-if="isMaintainer"
                  scope="col"
                  class="testing-env__col-actions"
                >
                  <span class="shift">{{ strings.actions }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <TestingRow
                v-for="pr in prs"
                :key="pr.pr"
                :pr="pr"
                :maintainer="isMaintainer"
                :busy="busy"
                :strings="strings"
                @toggle="togglePr"
                @update="updatePr"
                @remove="removePr"
              />
            </tbody>
          </table>
        </div>
        <p
          v-else
          class="testing-env__blank"
        >
          {{ strings.noPrs }}
        </p>
      </div>

      <DeploySection
        :payload="payload"
        :maintainer="isMaintainer"
        :busy="busy"
        :strings="strings"
        :jenkins_url="jenkinsUrl"
        @deploy="deploy"
        @refresh="refresh"
      />
    </template>

    <div
      v-if="toast"
      class="testing-env__toast"
      role="status"
      aria-live="polite"
    >
      {{ toast }}
    </div>
  </section>
</template>

<script>
import TestingRow from './TestingEnvironment/TestingRow.vue';
import DeploySection from './TestingEnvironment/DeploySection.vue';
import {
    DEFAULT_STRINGS,
    actionResultMessage,
    decodeAndParseJSON,
    effectiveActive,
    getTestingStatus,
    postAction,
    safeHttpUrl,
    sprintf
} from './TestingEnvironment/utils.js';

export default {
    name: 'TestingEnvironment',
    components: {
        TestingRow,
        DeploySection
    },
    props: {
        maintainer: {
            type: String,
            default: 'false'
        },
        jenkins_url: {
            type: String,
            default: ''
        },
        /**
         * URI encoded JSON string of translated panel strings.
         *
         * @see render_component() in openlibrary/plugins/upstream/utils.py
         */
        i18n: {
            type: String,
            default: ''
        }
    },
    data() {
        return {
            view: 'loading', // 'loading' | 'error' | 'ready'
            payload: null,
            busy: false,
            toast: '',
            addInput: '',
            strings: { ...DEFAULT_STRINGS },
            lastFocusRefresh: 0
        };
    },
    computed: {
        isMaintainer() {
            return this.maintainer === 'true';
        },
        prs() {
            // Merged PRs land in the next deploy regardless of this panel, so
            // the row is noise — the deploy plan still lists them as removals.
            return ((this.payload && this.payload.prs) || []).filter((pr) => pr.merged !== true);
        },
        jenkinsUrl() {
            return safeHttpUrl(this.jenkins_url);
        }
    },
    created() {
        try {
            const parsed = decodeAndParseJSON(this.i18n);
            if (parsed && typeof parsed === 'object') {
                this.strings = { ...DEFAULT_STRINGS, ...parsed };
            }
        } catch {
            // A malformed translation payload falls back to English.
        }
    },
    mounted() {
        this.bindFocusRefresh();
        this.loadStatus();
    },
    beforeUnmount() {
        document.removeEventListener('visibilitychange', this.onVisibility);
        window.removeEventListener('focus', this.onFocusRefresh);
    },
    methods: {
        text(key, ...args) {
            return sprintf(this.strings[key] || DEFAULT_STRINGS[key] || key, ...args);
        },
        setToast(message) {
            this.toast = message;
        },
        async loadStatus(showLoading = false, renderError = true, manageBusy = true) {
            if (manageBusy) this.busy = true;
            if (showLoading) this.view = 'loading';
            try {
                const payload = await getTestingStatus();
                // A refresh that returned the same state must not re-render:
                // swapping in a fresh object identity repaints the whole panel
                // even when nothing changed — that repaint is the flash you see
                // returning to the tab. Skip the assignment so Vue has nothing
                // to patch.
                if (!this.payload || JSON.stringify(payload) !== JSON.stringify(this.payload)) {
                    this.payload = payload;
                }
                this.view = 'ready';
                return true;
            } catch {
                if (renderError) this.view = 'error';
                return false;
            } finally {
                if (manageBusy) this.busy = false;
            }
        },
        async runAction(action, fields, message) {
            if (this.busy) return;
            this.busy = true;
            this.setToast(message);
            try {
                const response = await postAction(action, fields);
                const loaded = await this.loadStatus(false, false, false);
                this.setToast(loaded ? actionResultMessage(action, response.url, this.strings) : this.strings.loadError);
            } catch {
                this.setToast(this.strings.actionFailed);
            } finally {
                this.busy = false;
            }
        },
        togglePr(pr) {
            const action = effectiveActive(pr) ? '/status/disable' : '/status/enable';
            const verb = action.endsWith('disable') ? this.strings.disabling : this.strings.enabling;
            this.runAction(action, { prs: [pr.pr] }, sprintf(verb, pr.pr));
        },
        updatePr(pr) {
            this.runAction('/status/pull-latest', { prs: [pr.pr] }, sprintf(this.strings.updating, pr.pr));
        },
        removePr(pr) {
            this.runAction('/status/remove', { prs: [pr.pr] }, sprintf(this.strings.removing, pr.pr));
        },
        deploy() {
            this.runAction('/status/deploy', {}, this.strings.deploying);
        },
        refresh() {
            this.runAction('/status/refresh', {}, `${this.strings.refresh}…`);
        },
        addPrs() {
            const value = this.addInput.trim();
            if (!value) return;
            this.addInput = '';
            this.runAction('/status/add', { pr: value }, this.strings.adding);
        },
        retry() {
            this.loadStatus(true);
        },
        /**
         * Re-fetch when the tab regains focus, so state that changed while the
         * user was elsewhere (a deploy finishing, a PR being merged) shows up
         * without an interval timer. A short dedupe window absorbs browsers
         * that fire both `visibilitychange` and `focus` for one return.
         */
        bindFocusRefresh() {
            this.onVisibility = () => {
                if (document.visibilityState === 'visible') this.refreshIfVisible();
            };
            this.onFocusRefresh = () => this.refreshIfVisible();
            document.addEventListener('visibilitychange', this.onVisibility);
            window.addEventListener('focus', this.onFocusRefresh);
        },
        refreshIfVisible() {
            if (!this.$el.isConnected || this.busy || document.hidden) return;
            const now = Date.now();
            if (now - this.lastFocusRefresh < 2000) return;
            this.lastFocusRefresh = now;
            // manageBusy=false: a background fetch must not disable every
            // button in the panel for its duration — that dim is the flash
            // you see returning to the tab. It also keeps a failed silent
            // refresh from leaving the UI locked.
            this.loadStatus(false, false, false);
        }
    }
};
</script>

<!-- The component renders inside its own shadow root, so these rules style
     the whole panel (including subcomponent content) without touching the
     page around it. Inherited design tokens (--color-*, --spacing-*) cross
     the shadow boundary from the page. -->
<style>
:host {
  display: block;
}

/* One card in two bands: the set you are staging, then the apply step that
   flushes it. The root is just their container — it carries no surface of its
   own, and the toast sits below the card entirely. */
.testing-env {
  margin-bottom: var(--spacing-xl);
}

/* Top band: square along the bottom, where the deploy section joins it.
   overflow so the table's square corners are clipped by the card's. */
.testing-env__main {
  border: var(--border-width-thin) solid var(--color-border-subtle);
  border-bottom: 0;
  border-radius: var(--border-radius-card) var(--border-radius-card) 0 0;
  background: var(--color-surface);
  overflow: hidden;
}

/* ── Header bar ─────────────────────────────────────────────── */

.testing-env__bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  align-items: center;
  justify-content: space-between;
  /* Horizontal padding matches the table cells' so the title lines up with
     the first column. */
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: var(--border-width-thin) solid var(--color-border-subtle);
}

.testing-env__title {
  margin: 0;
  font-family: var(--font-family-heading);
  font-size: 1.2rem;
}

.testing-env__status {
  display: inline-flex;
  gap: var(--spacing-2xs);
  align-items: center;
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--border-radius-chip);
  background: var(--color-success-bg);
  color: var(--color-success-fg);
  font-size: 0.8rem;
  font-weight: 600;
}

.testing-env__status--idle {
  background: var(--color-surface-sunken);
  color: var(--color-text-muted);
}

.testing-env__dot {
  width: 7px;
  height: 7px;
  border-radius: var(--border-radius-circle);
  background: currentcolor;
}

/* ── Buttons ────────────────────────────────────────────────── */

.testing-env__btn {
  display: inline-flex;
  gap: var(--spacing-inline-md);
  align-items: center;
  justify-content: center;
  height: var(--control-height-medium);
  padding: 0 var(--spacing-md);
  border: var(--border-width-control) solid var(--color-border-subtle);
  border-radius: var(--border-radius-button);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-family-button);
  font-size: var(--font-size-body-medium);
  white-space: nowrap;
  cursor: pointer;
}

.testing-env__btn:focus-visible {
  outline: var(--focus-width) solid var(--color-focus-ring);
  outline-offset: 1px;
}

/* Busy and empty states are steady states, not error feedback. */
.testing-env__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.testing-env__btn:hover:not(:disabled) {
  background: var(--color-control-hover);
}

/* flex:none so the icon keeps its box when the label wraps or the button is
   squeezed — an SVG in a flex row is otherwise fair game for shrinking. */
.testing-env__btn-icon {
  flex: none;
}

.testing-env__btn--small {
  height: var(--control-height-small);
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-label-medium);
}

.testing-env__btn--primary {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: var(--color-text-inverse);
}

.testing-env__btn--primary:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
  background: var(--color-primary-hover);
}

/* ── Row on/off switch ──────────────────────────────────────── */

/* A button painted as a switch. aria-pressed is the state it shows; clicking
   it flips the row either way. */
.testing-env__switch {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 20px;
  padding: 0;
  /* Edge, not outline: the off fill sits near the row surface so it needs a
     border the on state doesn't — mixed toward the fill so it reads as the
     shape's own edge instead of a dark ring around it. */
  border: var(--border-width-control) solid
    color-mix(in srgb, var(--color-border) 45%, var(--color-neutral-object));
  border-radius: var(--border-radius-pill);
  background: var(--color-neutral-object);
  cursor: pointer;
}

.testing-env__switch[aria-pressed="true"] {
  border-color: var(--color-success-object);
  background: var(--color-success-object);
}

.testing-env__switch:focus-visible {
  outline: var(--focus-width) solid var(--color-focus-ring);
  outline-offset: 2px;
}

.testing-env__switch-knob {
  position: absolute;
  top: 50%;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: var(--border-radius-circle);
  background: var(--color-surface);
  transform: translateY(-50%);
  transition: left 0.12s;
}

.testing-env__switch[aria-pressed="true"] .testing-env__switch-knob {
  left: 16px;
}

@media (prefers-reduced-motion: reduce) {
  .testing-env__switch-knob {
    transition: none;
  }
}

/* ── Add-PR form ────────────────────────────────────────────── */

/* Rides on the right of the header bar; grows into the space the title
   leaves, capped so it stops short of the full width on a wide viewport. */
.testing-env__add {
  display: flex;
  flex: 1 1 20rem;
  gap: var(--spacing-sm);
  align-items: center;
  justify-content: flex-end;
  max-width: 32rem;
  margin: 0;
}

.testing-env__input {
  flex: 1;
  min-width: 0;
  height: var(--control-height-medium);
  margin: 0;
  padding: 0 var(--spacing-md);
  border: var(--border-width-control) solid var(--color-border-subtle);
  border-radius: var(--border-radius-input);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-family-body);
  font-size: 0.85rem;
}

.testing-env__input:focus-visible {
  outline: var(--focus-width) solid var(--color-focus-ring);
  outline-offset: 1px;
}

/* ── Table ──────────────────────────────────────────────────── */

.testing-env__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.testing-env__table th {
  padding: var(--spacing-xs) var(--spacing-md);
  border-bottom: var(--border-width-thin) solid var(--color-border-subtle);
  color: var(--color-text-muted);
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-align: left;
  text-transform: uppercase;
  white-space: nowrap;
}

.testing-env__table td {
  padding: var(--spacing-xs) var(--spacing-md);
  border: 0;
  border-bottom: var(--border-width-thin) solid var(--color-border-subtle);
  vertical-align: middle;
}

/* Plain surface is the resting state for a row — a tint means something is
   true of this row beyond "it's on the box". */
.testing-env__row td {
  background: var(--color-surface);
}

/* Blue for staged-but-not-deployed. A new row is always pending, so both
   classes land on the same tint. */
.testing-env__row.is-new td,
.testing-env__row.is-pending td {
  background: var(--color-primary-subtle);
}

/* Every column but the PR title is sized to its content, so the title keeps
   all the slack. */
.testing-env__col-toggle,
.testing-env__col-actions,
.testing-env__drift-cell {
  width: 1%;
  white-space: nowrap;
}

/* The toggle column is wider than the switch (its header is the longest
   content), so the cell centres it like the person columns centre avatars. */
.testing-env__col-toggle {
  text-align: center;
}

/* Trailing verb column: ragged-right. */
.testing-env__col-actions {
  text-align: right;
}

/* ── Cell contents ──────────────────────────────────────────── */

/* The one elastic column: every other cell is nowrap content sized to fit, so
   giving this one the leftover width keeps titles on a single line. */
.testing-env__pr-cell {
  width: 100%;
}

/* Fixed rail so titles line up down the column regardless of PR number width. */
.testing-env__pr-line {
  display: grid;
  grid-template-columns: 4.25em minmax(0, 1fr);
  gap: var(--spacing-sm);
  align-items: baseline;
}

/* The number and its live dot share the fixed rail; the dot is sized to sit
   inside the rail without widening it or shifting the title. */
.testing-env__pr-ref {
  display: inline-flex;
  gap: var(--spacing-2xs);
  align-items: center;
  min-width: 0;
}

.testing-env__pr-num,
.testing-env__pr-num:link,
.testing-env__pr-num:visited {
  color: var(--color-text-muted);
  font-family: var(--font-family-code);
  font-size: 0.78rem;
  white-space: nowrap;
  text-decoration: none;
}

/* Clamped at three lines — enough for any real PR title to wrap in full while
   still bounding row height. The full title rides in the link's title
   attribute for the rare one that clips. */
.testing-env__pr-title,
.testing-env__pr-title:link,
.testing-env__pr-title:visited {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
  color: var(--color-text);
  font-weight: 500;
  text-decoration: none;
}

.testing-env__pr-num:hover,
.testing-env__pr-num:focus-visible,
.testing-env__pr-title:hover,
.testing-env__pr-title:focus-visible {
  text-decoration: underline;
}

/* A filled dot marks a PR the last deploy put on the box — it is running now.
   Sits ahead of the number inside the fixed rail so it never shifts the
   title. A muted ring keeps it visible on the pending tint. */
.testing-env__live-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--border-radius-circle);
  background: var(--color-success-object);
  box-shadow: 0 0 0 2px var(--color-primary-subtle);
  flex: none;
}

.testing-env__person {
  display: inline-flex;
  gap: var(--spacing-2xs);
  align-items: center;
  white-space: nowrap;
}

.testing-env__avatar {
  border-radius: var(--border-radius-avatar);
}

/* Letter tile for a person the API has no picture for — same slot as the
   photo, username on hover like the real avatars. */
.testing-env__avatar--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--color-surface-sunken);
  color: var(--color-text-secondary);
  font-size: 0.7rem;
  font-weight: 600;
  line-height: 1;
}

/* The header text is wider than a 24px tile, so left alignment would leave
   the pictures hugging the PR-title column — centre them in their column. */
.testing-env__col-person {
  text-align: center;
}

/* The person cells centre their content, so the dash sits with the pictures
   automatically. */
.testing-env__empty {
  display: inline-block;
  color: var(--color-text-muted);
}

/* ── Cell stacks ────────────────────────────────────────────── */

/* The drift cell reads [pill] [update] [hourglass], each in its own fixed
   track, so the arrow and the hourglass line up down the table even when a
   row shows only one of them — a flex stack would leave the second one
   hugging the pill at a different x than its neighbours. Never set
   display:grid on a <td> — it overrides display:table-cell and drops the cell
   out of the table layout. Grid the wrapper inside instead. */
.testing-env__cell-stack {
  display: grid;
  grid-template-columns: 3.25em 28px 1.1em;
  gap: var(--spacing-xs);
  align-items: center;
}

.testing-env__drift-cell .testing-env__row-action {
  grid-column: 2;
}

.testing-env__drift-cell .testing-env__pending {
  grid-column: 3;
  justify-self: center;
}

/* min-width so a one-glyph verdict ("?") reads as the same chip as "-12". */
.testing-env__pill {
  display: inline-block;
  min-width: 3.25em;
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--border-radius-chip);
  font-size: 0.72rem;
  font-weight: 600;
  text-align: center;
  white-space: nowrap;
}

/* Each modifier publishes its foreground as --pill-fg so the linked-pill rule
   below can keep a pill's own colour without restating it per modifier. */
.testing-env__pill--ok {
  --pill-fg: var(--color-success-fg);

  background: var(--color-success-bg);
  color: var(--pill-fg);
}

.testing-env__pill--behind {
  --pill-fg: var(--color-warning-fg);

  background: var(--color-warning-bg);
  color: var(--pill-fg);
}

.testing-env__pill--unknown {
  --pill-fg: var(--color-text-muted);

  background: var(--color-surface-sunken);
  color: var(--pill-fg);
}

/* A linked pill keeps its own colour instead of the global link blue, so the
   two that navigate (behind → the compare view, unknown → the pinned commit)
   still read as chips. */
a.testing-env__pill:link,
a.testing-env__pill:visited {
  color: var(--pill-fg);
  text-decoration: none;
}

a.testing-env__pill:hover,
a.testing-env__pill:focus-visible {
  text-decoration: underline;
}

/* The hourglass marks a change the next deploy will apply; the wording rides
   in the title/aria-label. Sized as a small icon rather than inline text. */
.testing-env__pending {
  color: var(--color-warning-fg);
  font-size: 0.85rem;
  line-height: 1;
  white-space: nowrap;
}

/* Icon-only row actions (update to latest, remove from the set) — quiet
   buttons that surface their meaning on hover: blue for update, red for
   remove. The username/tooltip rides in the title attribute. */
.testing-env__row-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--border-radius-button);
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.testing-env__row-action:hover:not(:disabled) {
  background: var(--color-control-hover);
  color: var(--color-link);
}

.testing-env__row-action--danger:hover:not(:disabled) {
  background: var(--color-error-bg);
  color: var(--color-error-fg);
}

.testing-env__row-action + .testing-env__row-action {
  margin-left: var(--spacing-sm);
}

.testing-env__row-action:focus-visible {
  outline: var(--focus-width) solid var(--color-focus-ring);
  outline-offset: 1px;
}

/* ── Paused rows ────────────────────────────────────────────── */

/* A paused PR isn't on the box, so its row drains of color — grey fill, grey
   text, grey avatars, unfilled pills. Text is mixed toward the row fill rather
   than set to a flat grey, so everything sits a shade lighter than muted.
   Deliberately not row-wide opacity: the toggle you resume it with has to stay
   crisp. Late in the file so this outranks the pending tint. */
.testing-env__row.is-inactive {
  --paused-text: color-mix(
    in srgb,
    var(--color-text-muted) 65%,
    var(--color-surface-sunken)
  );
  --paused-text-strong: color-mix(
    in srgb,
    var(--color-text-secondary) 70%,
    var(--color-surface-sunken)
  );
}

.testing-env__row.is-inactive td {
  background: var(--color-surface-sunken);
  color: var(--paused-text);
}

.testing-env__row.is-inactive .testing-env__pr-title {
  color: var(--paused-text-strong);
  font-weight: 400;
}

.testing-env__row.is-inactive .testing-env__avatar {
  filter: grayscale(1);
  opacity: 0.6;
}

.testing-env__row.is-inactive .testing-env__pill {
  background: none;
  color: var(--paused-text);
  font-weight: 400;
}

/* Still clickable, just not competing with the live rows for attention. */
.testing-env__row.is-inactive .testing-env__row-action {
  color: var(--paused-text-strong);
}

/* Last of the row backgrounds: pointer feedback beats every state tint. */
.testing-env__row:hover td {
  background: var(--color-control-hover);
}

/* ── Dropped rows ───────────────────────────────────────────── */

/* A PR removed from the set but still on the box: read-only, queued for the
   deploy to drop. It keeps the live dot (it is running) but loses the toggle,
   drift, and actions — the REMOVE chip and a strikethrough carry the verdict. */
.testing-env__row.is-dropped .testing-env__pr-title {
  color: var(--color-text-muted);
  text-decoration: line-through;
  text-decoration-color: var(--color-text-muted);
}

.testing-env__row.is-dropped .testing-env__pr-cell {
  background: var(--color-surface-sunken);
}

/* ── Empty state ────────────────────────────────────────────── */

.testing-env__blank {
  padding: var(--spacing-lg) var(--spacing-md);
  color: var(--color-text-muted);
}

/* ── Activity toast ─────────────────────────────────────────── */

/* Below the card, flush with its left edge. */
.testing-env__toast {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  margin: var(--spacing-md) 0 0;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--border-radius-notification);
  background: var(--color-text);
  color: var(--color-text-inverse);
  font-family: var(--font-family-code);
  font-size: 0.75rem;
  width: fit-content;
}

/* ── Deploy section ─────────────────────────────────────────── */

/* Bottom band of the card, closing it off. Its border-top is the only seam
   between staging and applying — the two are one object, read top to bottom:
   the button, what it will do, then when it last ran. */
.testing-env__deploy {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  align-items: flex-start;
  margin: 0;
  padding: var(--spacing-lg) var(--spacing-md);
  border: var(--border-width-thin) solid var(--color-border-subtle);
  border-radius: 0 0 var(--border-radius-card) var(--border-radius-card);
  background: var(--color-surface);
}

/* Card footer, ruled off from the plan above it. Full width so the rule spans
   the card rather than just the text — the column is flex-start aligned. */
.testing-env__deploy-state {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  align-items: center;
  width: 100%;
  padding-top: var(--spacing-md);
  border-top: var(--border-width-thin) solid var(--color-border-subtle);
}

/* Holds the Deploy and Refresh buttons side by side — flex so the pair reads
   as one action row with a breathing gap. */
.testing-env__deploy-action {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  margin: 0;
}

.testing-env__status--deploying {
  background: var(--color-warning-bg);
  color: var(--color-warning-fg);
}

.testing-env__status--deploying .testing-env__dot {
  animation: testing-env-pulse 1.6s ease-in-out infinite;
}

@keyframes testing-env-pulse {
  50% {
    opacity: 0.25;
  }
}

@media (prefers-reduced-motion: reduce) {
  .testing-env__status--deploying .testing-env__dot {
    animation: none;
  }
}

.testing-env__jenkins {
  font-size: 0.8rem;
}

/* Full width so the row rules span the card, not just the longest change. */
.testing-env__plan {
  width: 100%;
}

.testing-env__plan-head {
  margin: 0 0 var(--spacing-xs);
  color: var(--color-text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
}

.testing-env__plan-empty {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

/* No gap — the rows are separated by rules instead, which need to meet. */
/* Column tracks live on the list, not the row, so every change lines up on the
   same four rails however long its verb is — "UPDATE PIN" is twice the width of
   "ADD", and translations stretch further still. The rows opt into these tracks
   via subgrid below. */
.testing-env__plan-list {
  display: grid;
  grid-template-columns: max-content max-content minmax(0, 1fr) max-content;
  column-gap: var(--spacing-sm);
  margin: 0;
  padding: 0;
  list-style: none;
}

/* Flex is the pre-subgrid fallback: same row, approximate rails. */
.testing-env__change {
  display: flex;
  gap: var(--spacing-sm);
  align-items: baseline;
  padding: var(--spacing-xs) 0;
  font-size: 0.8rem;
}

/* The row stays a real box — it carries the divider and the padding — while its
   cells align to the list's tracks. display:contents would align them too, but
   at the cost of the <li>'s box and its semantics in the a11y tree. */
@supports (grid-template-columns: subgrid) {
  .testing-env__change {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
  }
}

/* Between rows only: the head above and the card footer below bring their own
   spacing, so a rule on the first or last would double up. */
.testing-env__change + .testing-env__change {
  border-top: var(--border-width-thin) solid var(--color-border-subtle);
}

/* min-width only matters to the flex fallback; under subgrid the track is
   already as wide as the longest verb. */
.testing-env__change-kind {
  flex: none;
  min-width: 6em;
  color: var(--color-text-muted);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.testing-env__change--add .testing-env__change-kind {
  color: var(--color-success-fg);
}

.testing-env__change--pin .testing-env__change-kind {
  color: var(--color-warning-fg);
}

.testing-env__change--remove .testing-env__change-kind {
  color: var(--color-primary-active);
}

.testing-env__change-pr,
.testing-env__change-pr:link,
.testing-env__change-pr:visited {
  flex: none;
  color: var(--color-text);
  font-family: var(--font-family-code);
  font-size: 0.78rem;
  text-decoration: none;
}

.testing-env__change-pr:hover,
.testing-env__change-pr:focus-visible {
  text-decoration: underline;
}

/* min-width:0 so the ellipsis actually engages inside the flex row. */
.testing-env__change-title {
  min-width: 0;
  overflow: hidden;
  color: var(--color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.testing-env__change-detail {
  flex: none;
  color: var(--color-text-muted);
  font-size: 0.72rem;
}

/* The plan is the only place a pinned SHA is spelled out — the table reduced
   it to a tooltip on the drift pill. */
.testing-env__change-detail--sha {
  font-family: var(--font-family-code);
  font-size: 0.75rem;
}

/* ── Narrow screens: let the table scroll rather than squash ── */

@media (max-width: 900px) {
  .testing-env__table-wrap {
    overflow-x: auto;
  }

  .testing-env__table {
    min-width: 960px;
  }
}
</style>
