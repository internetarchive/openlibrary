import { shallowRef } from 'vue';
import { effectiveActive, postAction } from '../utils.js';

// The action endpoints answer {"ok": false, "error": "<code>"} for
// business failures; map each code to the translated toast that
// explains it.
const ACTION_ERRORS = {
    add_failed: 'actionFailed',
    deploy_failed: 'deployFailedTrigger',
    deploy_unconfigured: 'deployUnconfigured'
};

/**
 * PR toggle, update, remove, deploy, refresh, and add actions.
 *
 * @param {object}  opts
 * @param {import('vue').ShallowRef<boolean>} opts.busy       — shared re-entrancy guard
 * @param {Function} opts.loadStatus — re-fetch after each action
 * @param {Function} opts.setToast   — show an error toast
 * @param {import('vue').ShallowRef<object>} opts.strings     — translated strings
 * @returns {object} action flags and methods
 */
export function useActions({ busy, loadStatus, setToast, strings }) {
    const refreshing = shallowRef(false);
    const adding = shallowRef(false);
    const deploying = shallowRef(false);
    const addInput = shallowRef('');

    function text(key, ...args) {
        const fmt = strings.value[key] || key;
        return String(fmt).replace(/%s/g, () => (args.length ? args.shift() : '%s'));
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

    return {
        refreshing,
        adding,
        deploying,
        addInput,
        togglePr,
        updatePr,
        removePr,
        deploy,
        refresh,
        addPrs
    };
}
