<script setup>
import { computed } from 'vue';
import PersonCell from './PersonCell.vue';
import {
    REPO_URL,
    canUpdate,
    driftPill,
    effectiveActive,
    sprintf
} from './utils.js';

defineOptions({ name: 'TestingRow' });

const props = defineProps({
    pr: {
        type: Object,
        required: true
    },
    maintainer: {
        type: Boolean,
        default: false
    },
    strings: {
        type: Object,
        required: true
    }
});

const emit = defineEmits(['toggle', 'update', 'remove', 'restore']);

const inSet = computed(() => props.pr.in_set !== false);

// A staged removal makes the row read-only until deploy or restore: the
// deploy drops it, so its toggle and pin controls would change nothing.
const removalStaged = computed(() => props.pr.pending_remove === true);

const liveNow = computed(() => props.pr.live_now === true);

const mergeConflict = computed(() => props.pr.merge_conflict === true);

// Red beats live-now: a conflicted PR never landed, so the dot says so
// even if a stale live flag would still claim it.
const dotLabel = computed(() => {
    if (mergeConflict.value) return text('mergeConflictDot', props.pr.pr);
    return liveNow.value ? props.strings.liveNow : props.strings.notLive;
});

// The switch shows what the next deploy leaves the row as: the staged
// toggle when one is pending (the server emits pending_active then),
// otherwise the live state. Clicking flips the row either way.
const isActive = computed(() => effectiveActive(props.pr));

// The server classifies what the next deploy does with this row in
// `action`; any non-empty value means a change is staged for it.
const pending = computed(() => Boolean(props.pr.action));

const canUpdatePr = computed(() => !removalStaged.value && canUpdate(props.pr));

const pill = computed(() => driftPill(props.pr, props.strings));

const prUrl = computed(() => `${REPO_URL}/pull/${encodeURIComponent(props.pr.pr)}`);

function text(key, ...args) {
    return sprintf(props.strings[key] || key, ...args);
}
</script>

<template>
  <tr class="testing-env__row">
    <td
      v-if="maintainer"
      class="testing-env__col-toggle"
    >
      <button
        v-if="inSet && !removalStaged"
        type="button"
        class="testing-env__switch"
        :aria-pressed="isActive ? 'true' : 'false'"
        :aria-label="text('prOnTesting', pr.pr)"
        @click="emit('toggle', pr)"
      >
        <span
          class="testing-env__switch-knob"
          aria-hidden="true"
        />
      </button>
    </td>
    <td class="testing-env__pr-cell">
      <div class="testing-env__pr-line">
        <span class="testing-env__pr-ref">
          <span
            class="testing-env__live-dot"
            :class="{
              'testing-env__live-dot--not-live': !liveNow && !mergeConflict,
              'testing-env__live-dot--conflict': mergeConflict
            }"
            role="img"
            :title="dotLabel"
            :aria-label="dotLabel"
          />
          <a
            class="testing-env__pr-num"
            :href="prUrl"
          >#{{ pr.pr }}</a>
        </span>
        <a
          class="testing-env__pr-title"
          :href="prUrl"
          :title="pr.title"
        >{{ pr.title }}</a>
      </div>
    </td>
    <td class="testing-env__col-person">
      <PersonCell
        :name="pr.author"
        :avatar="pr.author_avatar"
      />
    </td>
    <td class="testing-env__col-person">
      <PersonCell
        :name="pr.assignee"
        :avatar="pr.assignee_avatar"
      />
    </td>
    <td class="testing-env__drift-cell">
      <div class="testing-env__cell-stack">
        <template v-if="inSet">
          <a
            v-if="pill.href"
            class="testing-env__pill"
            :href="pill.href"
            :title="pill.title"
          >{{ pill.label }}</a>
          <span
            v-else
            class="testing-env__pill"
            :title="pill.title"
          >{{ pill.label }}</span>
          <button
            v-if="maintainer && canUpdatePr"
            type="button"
            class="testing-env__row-action"
            :title="strings.update"
            :aria-label="strings.update"
            @click="emit('update', pr)"
          >
            <svg
              class="testing-env__btn-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <line
                x1="12"
                y1="19"
                x2="12"
                y2="5"
              />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
          <span
            v-if="pr.closed"
            class="testing-env__pending testing-env__closed"
            role="img"
            :title="strings.closed"
            :aria-label="strings.closed"
          >⛔</span>
          <span
            v-else-if="pending"
            class="testing-env__pending"
            role="img"
            :title="strings.changeOnDeploy"
            :aria-label="strings.changeOnDeploy"
          >⏳</span>
        </template>
        <span
          v-else
          class="testing-env__empty"
        >—</span>
      </div>
    </td>
    <td
      v-if="maintainer"
      class="testing-env__col-actions"
    >
      <button
        v-if="inSet && !removalStaged"
        type="button"
        class="testing-env__row-action testing-env__row-action--danger"
        :title="strings.remove"
        :aria-label="strings.remove"
        @click="emit('remove', pr)"
      >
        <svg
          class="testing-env__btn-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <line
            x1="10"
            y1="11"
            x2="10"
            y2="17"
          />
          <line
            x1="14"
            y1="11"
            x2="14"
            y2="17"
          />
        </svg>
      </button>
      <button
        v-else-if="inSet"
        type="button"
        class="testing-env__row-action testing-env__row-action--restore"
        :title="strings.restore"
        :aria-label="strings.restore"
        @click="emit('restore', pr)"
      >
        <svg
          class="testing-env__btn-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <path d="M3 3v5h5" />
        </svg>
      </button>
    </td>
  </tr>
</template>
