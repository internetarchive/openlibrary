<script setup>
import { computed } from 'vue';
import { REPO_URL, formatTime, sprintf, timeAgo } from './utils.js';

defineOptions({ name: 'DeploySection' });

const props = defineProps({
    payload: {
        type: Object,
        required: true
    },
    // Wall-clock tick for the relative "X ago" labels; bumped by the parent
    // poll so they advance even when the payload is unchanged.
    now: {
        type: Number,
        default: () => Date.now()
    },
    maintainer: {
        type: Boolean,
        default: false
    },
    strings: {
        type: Object,
        required: true
    },
    jenkinsUrl: {
        type: String,
        default: ''
    },
    refreshing: {
        type: Boolean,
        default: false
    },
    deploying: {
        type: Boolean,
        default: false
    }
});

const emit = defineEmits(['deploy', 'refresh']);

const CHANGE_LABELS = {
    add: 'addChange',
    pin: 'updatePin',
    enable: 'enable',
    disable: 'disable',
    remove: 'remove'
};

const changes = computed(() => (props.payload && props.payload.pending_changes) || []);

const changeCount = computed(() => changes.value.length);

const changeHeading = computed(() => {
    const template = changeCount.value === 1 ? props.strings.changeOne : props.strings.changeMany;
    return sprintf(template, changeCount.value);
});

const deployResult = computed(() => (props.payload && props.payload.deploy_result) || '');

const deployFinishedAt = computed(() => (props.payload && props.payload.deploy_finished_at) || '');

const deployStage = computed(() => (props.payload && props.payload.deploy_stage) || '');

const deployer = computed(() => (props.payload && props.payload.deployed_by) || '');

function text(key, ...args) {
    return sprintf(props.strings[key] || key, ...args);
}

function changeLabel(kind) {
    const key = CHANGE_LABELS[kind];
    return key ? props.strings[key] : kind;
}

function changeKey(change) {
    return `${change.kind}-${change.pr}`;
}

function prUrl(pr) {
    return `${REPO_URL}/pull/${encodeURIComponent(pr)}`;
}
</script>

<template>
  <section class="testing-env__deploy">
    <div
      v-if="maintainer"
      class="testing-env__deploy-action"
    >
      <button
        type="button"
        class="testing-env__btn testing-env__btn--primary"
        :disabled="deploying || !changeCount"
        @click="emit('deploy')"
      >
        <span
          v-if="deploying"
          class="testing-env__btn-icon testing-env__spinner"
          aria-hidden="true"
        />
        <svg
          v-else
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
          <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
          <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09" />
          <path d="M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z" />
          <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05" />
        </svg>
        {{ strings.deploy }}
      </button>
      <button
        type="button"
        class="testing-env__btn"
        :disabled="refreshing"
        @click="emit('refresh')"
      >
        <span
          v-if="refreshing"
          class="testing-env__btn-icon testing-env__spinner"
          aria-hidden="true"
        />
        <svg
          v-else
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
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        {{ strings.refresh }}
      </button>
    </div>

    <div class="testing-env__plan">
      <p
        v-if="changes.length"
        class="testing-env__plan-head"
      >
        {{ changeHeading }}
      </p>
      <p
        v-else
        class="testing-env__plan-empty"
      >
        {{ strings.nothingToDeploy }}
      </p>
      <ul
        v-if="changes.length"
        class="testing-env__plan-list"
      >
        <li
          v-for="change in changes"
          :key="changeKey(change)"
          class="testing-env__change"
          :class="`testing-env__change--${change.kind}`"
        >
          <span class="testing-env__change-kind">{{ changeLabel(change.kind) }}</span>
          <a
            class="testing-env__change-pr"
            :href="prUrl(change.pr)"
          >#{{ change.pr }}</a>
          <span class="testing-env__change-title">{{ change.title }}</span>
          <span
            v-if="change.reason === 'merged'"
            class="testing-env__change-detail"
          >{{ strings.mergedToMaster }}</span>
          <span
            v-else-if="change.reason === 'closed'"
            class="testing-env__change-detail"
          >{{ strings.closedWithoutMerging }}</span>
          <span
            v-else-if="change.detail"
            class="testing-env__change-detail testing-env__change-detail--sha"
          >{{ change.detail }}</span>
        </li>
      </ul>
    </div>

    <div class="testing-env__deploy-state">
      <span
        v-if="deployResult === 'SUCCESS'"
        class="testing-env__status"
        :title="formatTime(deployFinishedAt)"
      >
        <span
          class="testing-env__dot"
          aria-hidden="true"
        />{{ deployer
          ? text('deploySucceededBy', timeAgo(deployFinishedAt, now), deployer)
          : text('deploySucceeded', timeAgo(deployFinishedAt, now)) }}
      </span>
      <span
        v-else-if="deployResult === 'FAILURE' || deployResult === 'ABORTED'"
        class="testing-env__status testing-env__status--failed"
        :title="formatTime(deployFinishedAt)"
      >
        <span
          class="testing-env__dot"
          aria-hidden="true"
        />{{ deployer
          ? text('deployFailedBy', timeAgo(deployFinishedAt, now), deployer)
          : text('deployFailed', timeAgo(deployFinishedAt, now)) }}
      </span>
      <span
        v-else-if="payload.deploying"
        class="testing-env__status testing-env__status--deploying"
        :title="formatTime(payload.deploy_started_at)"
      >
        <span
          class="testing-env__dot"
          aria-hidden="true"
        />{{ deployStage
          ? (deployer
            ? text('deployingStageBy', timeAgo(payload.deploy_started_at, now), deployStage, deployer)
            : text('deployingStage', timeAgo(payload.deploy_started_at, now), deployStage))
          : (deployer
            ? text('deployingStartedBy', timeAgo(payload.deploy_started_at, now), deployer)
            : text('deployingStarted', timeAgo(payload.deploy_started_at, now))) }}
      </span>
      <span
        v-else-if="payload.last_deploy_at"
        class="testing-env__status"
        :title="formatTime(payload.last_deploy_at)"
      >
        <span
          class="testing-env__dot"
          aria-hidden="true"
        />{{ deployer
          ? text('lastDeployBy', timeAgo(payload.last_deploy_at, now), deployer)
          : text('lastDeploy', timeAgo(payload.last_deploy_at, now)) }}
      </span>
      <span
        v-else
        class="testing-env__status testing-env__status--idle"
      >{{ strings.neverDeployed }}</span>
      <a
        v-if="jenkinsUrl"
        class="testing-env__jenkins"
        :href="jenkinsUrl"
        target="_blank"
        rel="noopener noreferrer"
      >{{ strings.viewJenkins }}</a>
    </div>
  </section>
</template>
