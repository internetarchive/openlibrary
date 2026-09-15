import { shallowRef } from 'vue';
import { actionErrorMessage, effectiveActive, postAction } from '../utils.js';

/**
 * PR toggle, update, remove, restore, deploy, refresh, and add actions.
 *
 * @param {object}  opts
 * @param {import('vue').ShallowRef<boolean>} opts.busy       — whether the action queue is processing
 * @param {Function} opts.loadStatus — re-fetch after each action
 * @param {Function} opts.setToast   — show an error toast
 * @param {object}  opts.strings     — translated strings (plain object, set once at setup)
 * @returns {object} action flags and methods
 */
export function useActions({ busy, loadStatus, setToast, strings }) {
    const refreshing = shallowRef(false);
    const adding = shallowRef(false);
    const deploying = shallowRef(false);
    const addInput = shallowRef('');
    const queue = [];
    let draining = false;

    function text(key, ...args) {
        const fmt = strings[key] || key;
        return String(fmt).replace(/%s/g, () => (args.length ? args.shift() : '%s'));
    }

    async function executeAction(action, fields) {
        try {
            const result = await postAction(action, fields);
            await loadStatus(false, false, false);
            // A business failure ({"ok": false, "error": "<code>"}) is a
            // completed request, not a thrown fetch — say why instead of
            // pretending the action landed.
            if (result && result.ok === false) {
                setToast(actionErrorMessage(result, strings));
                return result;
            }
            return result;
        } catch {
            setToast(text('actionFailed'));
            return false;
        }
    }

    async function drainQueue() {
        if (draining) return;
        draining = true;
        busy.value = true;
        try {
            while (queue.length) {
                const item = queue.shift();
                const result = await executeAction(item.action, item.fields);
                item.waiters.forEach(({ resolve }) => resolve(result));
            }
        } finally {
            draining = false;
            busy.value = false;
        }
    }

    /**
     * Queue mutations so rapid clicks are not silently dropped. Consecutive
     * pull-latest actions share one request; deploy and other actions remain
     * ordered queue barriers.
     */
    function enqueue(action, fields, kind = 'action') {
        const waiter = new Promise((resolve) => {
            const last = queue[queue.length - 1];
            if (kind === 'pull-latest' && last?.kind === kind) {
                last.fields.prs.push(...fields.prs);
                last.waiters.push({ resolve });
            } else {
                queue.push({ action, fields, kind, waiters: [{ resolve }] });
            }
        });
        drainQueue();
        return waiter;
    }

    function togglePr(pr) {
        const action = effectiveActive(pr) ? '/status/disable' : '/status/enable';
        enqueue(action, { prs: [pr.pr] });
    }

    function updatePr(pr) {
        enqueue('/status/pull-latest', { prs: [pr.pr] }, 'pull-latest');
    }

    function removePr(pr) {
        enqueue('/status/remove', { prs: [pr.pr] });
    }

    // Undo a staged removal: the server just clears the flag, so the row's
    // pinned commit and toggle state come back untouched.
    function restorePr(pr) {
        enqueue('/status/restore', { prs: [pr.pr] });
    }

    async function deploy() {
        deploying.value = true;
        try {
            await enqueue('/status/deploy', {});
        } finally {
            deploying.value = false;
        }
    }

    async function refresh() {
        refreshing.value = true;
        try {
            await enqueue('/status/refresh', {});
        } finally {
            refreshing.value = false;
        }
    }

    async function addPrs() {
        if (adding.value) return;
        const value = addInput.value.trim();
        if (!value) return;
        adding.value = true;
        try {
            const result = await enqueue('/status/add', { pr: value });
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
        restorePr,
        deploy,
        refresh,
        addPrs
    };
}
