<script setup>
import { shallowRef, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import TestingRow from './TestingEnvironment/TestingRow.vue';
import DeploySection from './TestingEnvironment/DeploySection.vue';
import {
    DEFAULT_STRINGS,
    applyDeployBadge,
    decodeAndParseJSON,
    effectiveActive,
    faviconEnv,
    getTestingStatus,
    postAction,
    sprintf
} from './TestingEnvironment/utils.js';

// The action endpoints answer {"ok": false, "error": "<code>"} for business
// failures; map each code to the translated toast that explains it.
const ACTION_ERRORS = {
    add_failed: 'actionFailed',
    deploy_failed: 'deployFailedTrigger',
    deploy_unconfigured: 'deployUnconfigured'
};

defineOptions({ name: 'TestingEnvironment' });

const props = defineProps({
    maintainer: {
        type: String,
        default: 'false'
    },
    jenkinsUrl: {
        type: String,
        default: ''
    },
    /** URI-encoded JSON of translated panel strings.
     * @see render_component() in openlibrary/plugins/upstream/utils.py */
    i18n: {
        type: String,
        default: ''
    }
});

// ── Reactive state ──────────────────────────────────────────────────
const view = shallowRef('loading'); // 'loading' | 'error' | 'ready'
const payload = shallowRef(null);
const busy = shallowRef(false);
const refreshing = shallowRef(false);
const adding = shallowRef(false);
const deploying = shallowRef(false);
const addInput = shallowRef('');
const strings = shallowRef({ ...DEFAULT_STRINGS });
const toast = shallowRef('');
// Wall-clock tick for the relative "X ago" deploy labels. Bumped by
// the same poll that refreshes data, so the labels advance even when
// the payload is unchanged (loadStatus skips identical JSON).
const now = shallowRef(Date.now());

// ── Non-reactive instance state (plain let, not refs) ──────────────
let timer = null;
let toastTimer = null;
let deployBadge = null;

// ── Computed ────────────────────────────────────────────────────────
const isMaintainer = computed(() => props.maintainer === 'true');

const prs = computed(() => {
    // Merged PRs land in the next deploy regardless; the row is noise.
    return ((payload.value && payload.value.prs) || []).filter((pr) => pr.merged !== true);
});

// ── Watchers ────────────────────────────────────────────────────────
// The tab favicon follows the deploy: spinner-ring variant while a
// build is presumed running, the normal one when it finishes.
watch(
    () => payload.value?.deploying,
    (deploying) => syncDeployFavicon(deploying),
    { immediate: true }
);

// ── Methods ─────────────────────────────────────────────────────────
function text(key, ...args) {
    return sprintf(strings.value[key] || DEFAULT_STRINGS[key] || key, ...args);
}

function setToast(message) {
    toast.value = message;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        toast.value = '';
    }, 6000);
}

// Mark the page favicon while a deploy runs: the real favicon is drawn
// once with a static badge wedge and swapped into the rel="icon" links
// (a static mark is one render at start and one swap at the end — no
// animation loop for a throttled tab to stall). Only openlibrary
// favicons are touched; the badge is removed when the deploy ends or
// the panel unmounts.
function syncDeployFavicon(isDeploying) {
    if (isDeploying) {
        if (deployBadge) return;
        const links = Array.from(document.querySelectorAll('link[rel="icon"]'))
            .filter((link) => faviconEnv(link.getAttribute('href')));
        if (!links.length) return;
        deployBadge = applyDeployBadge(links);
    } else if (deployBadge) {
        deployBadge();
        deployBadge = null;
    }
}

function onVisibilityChange() {
    if (document.visibilityState === 'visible') {
        now.value = Date.now();
        silentRefresh();
    }
}

// Re-fetch quietly: no loading view, no error takeover, no busy flag —
// loadStatus(false, false, false). Skipped while an action is in flight.
function silentRefresh() {
    if (busy.value) return;
    loadStatus(false, false, false);
}

async function loadStatus(showLoading = false, renderError = true, manageBusy = true) {
    // busy is a re-entrancy guard and aria-busy signal only.
    if (manageBusy) busy.value = true;
    if (showLoading) view.value = 'loading';
    try {
        const newPayload = await getTestingStatus();
        // Skip the assignment when nothing changed — a fresh object
        // identity would repaint the panel (the flash on tab return).
        if (!payload.value || JSON.stringify(newPayload) !== JSON.stringify(payload.value)) {
            payload.value = newPayload;
        }
        view.value = 'ready';
        return true;
    } catch {
        if (renderError) view.value = 'error';
        return false;
    } finally {
        if (manageBusy) busy.value = false;
    }
}

async function runAction(action, fields) {
    if (busy.value) return false;
    busy.value = true;
    try {
        const result = await postAction(action, fields);
        await loadStatus(false, false, false);
        // A business failure ({"ok": false, "error": "<code>"}) is a
        // completed request, not a thrown fetch — say why instead of
        // pretending the action landed.
        if (result && result.ok === false) {
            const key = ACTION_ERRORS[result.error] || 'actionFailed';
            setToast(text(key));
            return result;
        }
        return result;
    } catch {
        setToast(text('actionFailed'));
        return false;
    } finally {
        busy.value = false;
    }
}

function togglePr(pr) {
    const action = effectiveActive(pr) ? '/status/disable' : '/status/enable';
    runAction(action, { prs: [pr.pr] });
}

function updatePr(pr) {
    runAction('/status/pull-latest', { prs: [pr.pr] });
}

function removePr(pr) {
    runAction('/status/remove', { prs: [pr.pr] });
}

async function deploy() {
    if (busy.value) return;
    deploying.value = true;
    try {
        await runAction('/status/deploy', {});
    } finally {
        deploying.value = false;
    }
}

async function refresh() {
    if (busy.value) return;
    refreshing.value = true;
    try {
        await runAction('/status/refresh', {});
    } finally {
        refreshing.value = false;
    }
}

async function addPrs() {
    if (adding.value || busy.value) return;
    const value = addInput.value.trim();
    if (!value) return;
    adding.value = true;
    try {
        const result = await runAction('/status/add', { pr: value });
        // A failed add keeps the input so it's obvious the PR didn't land.
        if (result && result.ok) {
            addInput.value = '';
        }
    } finally {
        adding.value = false;
    }
}

function retry() {
    loadStatus(true);
}

// ── Lifecycle ───────────────────────────────────────────────────────
// Parse the i18n translation payload (runs at setup time — same timing
// as the old `created` hook).
try {
    const parsed = decodeAndParseJSON(props.i18n);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        strings.value = { ...DEFAULT_STRINGS, ...parsed };
    }
} catch {
    // A malformed translation payload falls back to English.
}

onMounted(() => {
    loadStatus();
    // Single 1s interval: bumps `now` every tick (advances the label, no
    // network), and refreshes data only on a tick at a :05 clock boundary.
    timer = setInterval(() => {
        now.value = Date.now();
        if (Math.floor(now.value / 1000) % 5 === 0) {
            silentRefresh();
        }
    }, 1000);
    document.addEventListener('visibilitychange', onVisibilityChange);
});

onBeforeUnmount(() => {
    clearTimeout(toastTimer);
    clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    syncDeployFavicon(false);
});
</script>

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
        :jenkins-url="jenkinsUrl"
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

<!-- Shadow-DOM styles: rules here style the whole panel; inherited design
     tokens (--color-*, --spacing-*) cross the shadow boundary. The rules live
     in styles.css; <style src> inlines them into this custom element's shadow
     root at build time, so the encapsulation choice is unchanged. -->
<style src="./TestingEnvironment/styles.css"></style>
