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
              :disabled="adding"
            >
              <span
                v-if="adding"
                class="testing-env__btn-icon testing-env__spinner"
                aria-hidden="true"
              />
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
        :now="now"
        :maintainer="isMaintainer"
        :strings="strings"
        :jenkins_url="jenkinsUrl"
        :refreshing="refreshing"
        :deploying="deploying"
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
    decodeAndParseJSON,
    effectiveActive,
    getTestingStatus,
    postAction,
    safeHttpUrl,
    sprintf
} from './TestingEnvironment/utils.js';

// The action endpoints answer {"ok": false, "error": "<code>"} for business
// failures; map each code to the translated toast that explains it.
const ACTION_ERRORS = {
    add_failed: 'actionFailed',
    deploy_failed: 'deployFailedTrigger',
    deploy_unconfigured: 'deployUnconfigured'
};

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
            adding: false,
            deploying: false,
            addInput: '',
            strings: { ...DEFAULT_STRINGS },
            toast: '',
            toastTimer: null,
            // Wall-clock tick for the relative "X ago" deploy labels. Bumped by
            // the same poll that refreshes data, so the labels advance even when
            // the payload is unchanged (loadStatus skips identical JSON).
            now: Date.now()
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
        // Silent background refresh: every 5s and whenever the tab regains
        // focus, re-fetch so drift/deploy state stays fresh. No spinner — the
        // explicit Refresh button is the only thing that spins, and an action in
        // flight is left alone so this can't race the POST-triggered reload.
        this._refreshTimer = setInterval(() => {
            this.now = Date.now();
            this.silentRefresh();
        }, 5000);
        document.addEventListener('visibilitychange', this.onVisibilityChange);
    },
    beforeUnmount() {
        clearTimeout(this.toastTimer);
        clearInterval(this._refreshTimer);
        document.removeEventListener('visibilitychange', this.onVisibilityChange);
    },
    methods: {
        text(key, ...args) {
            return sprintf(this.strings[key] || DEFAULT_STRINGS[key] || key, ...args);
        },
        setToast(message) {
            this.toast = message;
            clearTimeout(this.toastTimer);
            this.toastTimer = setTimeout(() => {
                this.toast = '';
            }, 6000);
        },
        onVisibilityChange() {
            if (document.visibilityState === 'visible') {
                this.now = Date.now();
                this.silentRefresh();
            }
        },
        // Re-fetch quietly: no loading view, no error takeover, no busy flag —
        // loadStatus(false, false, false). Skipped while an action is in flight.
        silentRefresh() {
            if (this.busy) return;
            this.loadStatus(false, false, false);
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
            if (this.busy) return false;
            this.busy = true;
            try {
                const result = await postAction(action, fields);
                await this.loadStatus(false, false, false);
                // A business failure ({"ok": false, "error": "<code>"}) is a
                // completed request, not a thrown fetch — say why instead of
                // pretending the action landed.
                if (result && result.ok === false) {
                    const key = ACTION_ERRORS[result.error] || 'actionFailed';
                    this.setToast(this.text(key));
                    return result;
                }
                return result;
            } catch {
                this.setToast(this.text('actionFailed'));
                return false;
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
        async deploy() {
            if (this.busy) return;
            this.deploying = true;
            try {
                await this.runAction('/status/deploy', {});
            } finally {
                this.deploying = false;
            }
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
        async addPrs() {
            if (this.adding || this.busy) return;
            const value = this.addInput.trim();
            if (!value) return;
            this.adding = true;
            try {
                const result = await this.runAction('/status/add', { pr: value });
                // A failed add keeps the input so it's obvious the PR didn't land.
                if (result && result.ok) {
                    this.addInput = '';
                }
            } finally {
                this.adding = false;
            }
        },
        retry() {
            this.loadStatus(true);
        }
    }
};
</script>

<!-- Shadow-DOM styles: rules here style the whole panel; inherited design
     tokens (--color-*, --spacing-*) cross the shadow boundary. The rules live
     in styles.css; <style src> inlines them into this custom element's shadow
     root at build time, so the encapsulation choice is unchanged. -->
<style src="./TestingEnvironment/styles.css"></style>
