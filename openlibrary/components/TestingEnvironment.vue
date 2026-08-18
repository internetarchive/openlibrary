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
        :strings="strings"
        :jenkins_url="jenkinsUrl"
        :refreshing="refreshing"
        @deploy="deploy"
        @refresh="refresh"
      />
    </template>
  </section>
</template>

<script>
import TestingRow from './TestingEnvironment/TestingRow.vue';
import DeploySection from './TestingEnvironment/DeploySection.vue';
import {
    DEFAULT_STRINGS,
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
        /** URI-encoded JSON of translated panel strings.
         * @see render_component() in openlibrary/plugins/upstream/utils.py */
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
            refreshing: false,
            addInput: '',
            strings: { ...DEFAULT_STRINGS }
        };
    },
    computed: {
        isMaintainer() {
            return this.maintainer === 'true';
        },
        prs() {
            // Merged PRs land in the next deploy regardless; the row is noise.
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
        this.loadStatus();
    },
    methods: {
        text(key, ...args) {
            return sprintf(this.strings[key] || DEFAULT_STRINGS[key] || key, ...args);
        },
        async loadStatus(showLoading = false, renderError = true, manageBusy = true) {
            // busy is a re-entrancy guard and aria-busy signal only.
            if (manageBusy) this.busy = true;
            if (showLoading) this.view = 'loading';
            try {
                const payload = await getTestingStatus();
                // Skip the assignment when nothing changed — a fresh object
                // identity would repaint the panel (the flash on tab return).
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
        async runAction(action, fields) {
            if (this.busy) return;
            this.busy = true;
            try {
                await postAction(action, fields);
                await this.loadStatus(false, false, false);
            } finally {
                this.busy = false;
            }
        },
        togglePr(pr) {
            const action = effectiveActive(pr) ? '/status/disable' : '/status/enable';
            this.runAction(action, { prs: [pr.pr] });
        },
        updatePr(pr) {
            this.runAction('/status/pull-latest', { prs: [pr.pr] });
        },
        removePr(pr) {
            this.runAction('/status/remove', { prs: [pr.pr] });
        },
        deploy() {
            this.runAction('/status/deploy', {});
        },
        async refresh() {
            if (this.busy) return;
            this.refreshing = true;
            try {
                await this.runAction('/status/refresh', {});
            } finally {
                this.refreshing = false;
            }
        },
        addPrs() {
            const value = this.addInput.trim();
            if (!value) return;
            this.addInput = '';
            this.runAction('/status/add', { pr: value });
        },
        retry() {
            this.loadStatus(true);
        }
    }
};
</script>

<!-- Shadow-DOM styles: rules here style the whole panel; inherited design
     tokens (--color-*, --spacing-*) cross the shadow boundary. -->
<style>
:host {
  display: block;
}

/* One card in two bands: the staged set on top, the apply step below. */
.testing-env {
  margin-bottom: var(--spacing-xl);
}

/* Top band: square bottom corners, where the deploy section joins. */
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
  /* Padding matches the table cells', so the title lines up with column one. */
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

/* flex:none so the icon isn't shrunk in its flex row. */
.testing-env__btn-icon {
  flex: none;
}

/* A simple border ring, spun — no icon needed. Only the explicit click sets
   `refreshing`, so nothing spins on focus. */
.testing-env__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: testing-env-spin 0.8s linear infinite;
}

@keyframes testing-env-spin {
  to {
    transform: rotate(360deg);
  }
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

/* A button painted as a switch; aria-pressed is the state it shows. */
.testing-env__switch {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 20px;
  padding: 0;
  /* Edge, not outline: the off fill sits on the row surface, so the border is
     mixed toward the fill. */
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

/* Right of the header bar; grows into the space the title leaves. */
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

/* Every column but the PR title is content-sized; the title takes the slack. */
.testing-env__col-toggle,
.testing-env__col-actions,
.testing-env__drift-cell {
  width: 1%;
  white-space: nowrap;
}

/* The toggle header is the widest content, so the cell centres the switch. */
.testing-env__col-toggle {
  text-align: center;
}

/* Trailing verb column: ragged-right. */
.testing-env__col-actions {
  text-align: right;
}

/* ── Cell contents ──────────────────────────────────────────── */

/* The one elastic column: leftover width keeps titles on a single line. */
.testing-env__pr-cell {
  width: 100%;
}

/* Fixed rail so titles line up regardless of PR-number width; the number and
   dot centre against a title that wraps. */
.testing-env__pr-line {
  display: grid;
  grid-template-columns: 4.25em minmax(0, 1fr);
  gap: var(--spacing-sm);
  align-items: center;
}

/* Number and live dot share the fixed rail, so the dot never shifts the title. */
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

/* Clamped at three lines to bound row height; the full title is in the link. */
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

/* Dot marks the PR's place in the last deploy: green when live now, gray when
   never deployed. Both render so the rail stays steady. */
.testing-env__live-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--border-radius-circle);
  background: var(--color-success-object);
  flex: none;
}

.testing-env__live-dot--not-live {
  background: var(--color-text-muted);
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

/* Letter tile when the API has no picture — same slot as the photo. */
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

/* The header is wider than the 24px tile, so centre the pictures in the column. */
.testing-env__col-person {
  text-align: center;
}

/* Person cells are centred, so the dash sits with the pictures. */
.testing-env__empty {
  display: inline-block;
  color: var(--color-text-muted);
}

/* ── Cell stacks ────────────────────────────────────────────── */

/* The drift cell reads [pill] [update] [hourglass], each in a fixed track so
   they line up down the table. Never set display:grid on a <td> — it drops
   the cell out of the table layout; grid the wrapper inside instead. */
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

/* Plain-text verdict — no chip. min-width keeps "?" aligned with "-12". */
.testing-env__pill {
  display: inline-block;
  min-width: 3.25em;
  font-size: 0.78rem;
  text-align: center;
  white-space: nowrap;
}

/* The behind/unknown pills link out; the rest are spans. Read as plain text. */
a.testing-env__pill:link,
a.testing-env__pill:visited {
  color: var(--color-text);
  text-decoration: none;
}

a.testing-env__pill:hover,
a.testing-env__pill:focus-visible {
  text-decoration: underline;
}

/* The hourglass marks a staged change; wording is in the title/aria-label. */
.testing-env__pending {
  color: var(--color-warning-fg);
  font-size: 0.85rem;
  line-height: 1;
  white-space: nowrap;
}

/* Icon-only row actions (update / remove): bordered buttons, blue for update,
   red for remove on hover; tooltips ride in the title attribute. */
.testing-env__row-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: var(--border-width-control) solid var(--color-border-subtle);
  border-radius: var(--border-radius-button);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.testing-env__row-action:hover:not(:disabled) {
  border-color: var(--color-link);
  background: var(--color-control-hover);
  color: var(--color-link);
}

.testing-env__row-action--danger:hover:not(:disabled) {
  border-color: var(--color-error-fg);
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

/* Last of the row backgrounds: pointer feedback beats every state tint. */
.testing-env__row:hover td {
  background: var(--color-control-hover);
}

/* ── Empty state ────────────────────────────────────────────── */

.testing-env__blank {
  padding: var(--spacing-lg) var(--spacing-md);
  color: var(--color-text-muted);
}

/* ── Deploy section ─────────────────────────────────────────── */

/* Bottom band of the card, closing it off: the button, what it will do, then
   when it last ran. */
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

/* Card footer, ruled off from the plan; full width so the rule spans the card. */
.testing-env__deploy-state {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  align-items: center;
  width: 100%;
  padding-top: var(--spacing-md);
  border-top: var(--border-width-thin) solid var(--color-border-subtle);
}

/* Deploy and Refresh side by side, as one action row. */
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
  .testing-env__status--deploying .testing-env__dot,
  .testing-env__spinner {
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

/* No gap — rows are separated by rules, which need to meet. Column tracks live
   on the list so every change lines up whatever its verb's width; the rows
   opt into those tracks via subgrid below. */
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

/* The row stays a real box — the divider and padding — while its cells align
   to the list's tracks. display:contents would drop the <li>'s a11y semantics. */
@supports (grid-template-columns: subgrid) {
  .testing-env__change {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
  }
}

/* Between rows only — the head and footer bring their own spacing. */
.testing-env__change + .testing-env__change {
  border-top: var(--border-width-thin) solid var(--color-border-subtle);
}

/* min-width only matters to the flex fallback; subgrid tracks fit the verb. */
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

/* The plan is the only place a pinned SHA is spelled out. */
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
