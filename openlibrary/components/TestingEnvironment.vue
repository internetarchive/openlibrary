<script setup>
import { shallowRef, computed, watch, onBeforeUnmount } from 'vue';
import TestingRow from './TestingEnvironment/TestingRow.vue';
import DeploySection from './TestingEnvironment/DeploySection.vue';
import { DEFAULT_STRINGS, applyDeployBadge, decodeAndParseJSON, faviconEnv } from './TestingEnvironment/utils.js';
import { useToast } from './TestingEnvironment/composables/useToast.js';
import { useTestingStatus } from './TestingEnvironment/composables/useTestingStatus.js';
import { useActions } from './TestingEnvironment/composables/useActions.js';

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

// ── i18n (runs at setup time — same timing as the old `created` hook) ─
// Plain object: translated strings are fixed at render time and never mutate,
// so a ref would add unnecessary proxy overhead.
let strings = { ...DEFAULT_STRINGS };
try {
    const parsed = decodeAndParseJSON(props.i18n);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        strings = { ...DEFAULT_STRINGS, ...parsed };
    }
} catch {
    // A malformed translation payload falls back to English.
}

// ── Composables ─────────────────────────────────────────────────────
const { toast, setToast } = useToast();

// busy is a shared re-entrancy guard between status fetching and actions.
const busy = shallowRef(false);
const { view, payload, now, loadStatus, retry } = useTestingStatus(busy);
const { refreshing, adding, deploying, addInput, togglePr, updatePr, removePr, deploy, refresh, addPrs } = useActions({
    busy,
    loadStatus,
    setToast,
    strings
});

// ── Derived state ───────────────────────────────────────────────────
const isMaintainer = computed(() => props.maintainer === 'true');

const prs = computed(() => {
    // Merged PRs land in the next deploy regardless; the row is noise.
    return ((payload.value && payload.value.prs) || []).filter((pr) => pr.merged !== true);
});

// ── Deploy favicon badge ────────────────────────────────────────────
let deployBadge = null;

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

watch(
    () => payload.value?.deploying,
    (deploying) => syncDeployFavicon(deploying),
    { immediate: true }
);

onBeforeUnmount(() => syncDeployFavicon(false));
</script>

<template>
  <section
    class="testing-env"
    :aria-busy="busy ? 'true' : 'false'"
  >
    <div
      v-if="view === 'loading'"
      class="testing-env__main"
    >
      <p
        class="testing-env__blank"
        role="status"
        aria-live="polite"
      >
        {{ strings.loading }}
      </p>
    </div>

    <div
      v-else-if="view === 'error'"
      class="testing-env__main"
    >
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

    <div
      v-else
    >
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
    </div>

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
