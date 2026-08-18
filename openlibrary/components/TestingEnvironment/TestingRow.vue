<template>
  <tr class="testing-env__row">
    <td
      v-if="maintainer"
      class="testing-env__col-toggle"
    >
      <button
        v-if="inSet"
        type="button"
        class="testing-env__switch"
        :aria-pressed="isActive ? 'true' : 'false'"
        :aria-label="text('prOnTesting', pr.pr)"
        @click="$emit('toggle', pr)"
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
            @click="$emit('update', pr)"
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
            v-if="pending"
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
        v-if="inSet"
        type="button"
        class="testing-env__row-action testing-env__row-action--danger"
        :title="strings.remove"
        :aria-label="strings.remove"
        @click="$emit('remove', pr)"
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
    </td>
  </tr>
</template>

<script>
import PersonCell from './PersonCell.vue';
import {
    REPO_URL,
    canUpdate,
    driftPill,
    effectiveActive,
    sprintf
} from './utils.js';

export default {
    name: 'TestingRow',
    components: {
        PersonCell
    },
    props: {
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
    },
    emits: ['toggle', 'update', 'remove'],
    computed: {
        inSet() {
            return this.pr.in_set !== false;
        },
        liveNow() {
            return this.pr.live_now === true;
        },
        mergeConflict() {
            return this.pr.merge_conflict === true;
        },
        // Red beats live-now: a conflicted PR never landed, so the dot says so
        // even if a stale live flag would still claim it.
        dotLabel() {
            if (this.mergeConflict) return this.strings.mergeConflict;
            return this.liveNow ? this.strings.liveNow : this.strings.notLive;
        },
        // The switch shows what the next deploy leaves the row as: the staged
        // toggle when one is pending (the server emits pending_active then),
        // otherwise the live state. Clicking flips the row either way.
        isActive() {
            return effectiveActive(this.pr);
        },
        // The server classifies what the next deploy does with this row in
        // `action`; any non-empty value means a change is staged for it.
        pending() {
            return Boolean(this.pr.action);
        },
        canUpdatePr() {
            return canUpdate(this.pr);
        },
        pill() {
            return driftPill(this.pr, this.strings);
        },
        prUrl() {
            return `${REPO_URL}/pull/${encodeURIComponent(this.pr.pr)}`;
        }
    },
    methods: {
        text(key, ...args) {
            return sprintf(this.strings[key] || key, ...args);
        }
    }
};
</script>
