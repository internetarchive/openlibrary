import { shallowRef } from 'vue';
import { actionErrorMessage, effectiveActive, parsePrNumbers, postAction } from '../utils.js';

// How long a newly added row stays highlighted. Purely client-side: a page
// refresh clears it, which is the intended behaviour.
const RECENT_HIGHLIGHT_MS = 10000;

/**
 * PR toggle, update, remove, restore, deploy, refresh, and add actions.
 *
 * @param {object}  opts
 * @param {import('vue').ShallowRef<boolean>} opts.busy       — whether the action queue is processing
 * @param {import('vue').Ref<object|null>} [opts.payload]     — panel payload; toggle/remove/restore flip it optimistically
 * @param {Function} opts.setToast   — show an error toast
 * @param {object}  opts.strings     — translated strings (plain object, set once at setup)
 * @returns {object} action flags and methods
 */
export function useActions({ busy, payload, setToast, strings }) {
    const refreshing = shallowRef(false);
    const adding = shallowRef(false);
    const deploying = shallowRef(false);
    const addInput = shallowRef('');
    // PR numbers added within the last RECENT_HIGHLIGHT_MS. Replaced rather
    // than mutated, because shallowRef does not track changes inside a Set.
    const recentlyAdded = shallowRef(new Set());
    const queue = [];
    let draining = false;

    function text(key, ...args) {
        const fmt = strings[key] || key;
        return String(fmt).replace(/%s/g, () => (args.length ? args.shift() : '%s'));
    }

    // No re-fetch here: the SSE stream delivers the confirmed snapshot
    // within ~1s (polling covers a dead stream), so a GET per action would
    // only duplicate it — and an intermediate GET predating queued requests
    // is exactly what flickered rapid toggles.
    async function executeAction(action, fields, method = 'POST') {
        try {
            const result = await postAction(action, fields, method);
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
                const result = await executeAction(item.action, item.fields, item.method);
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
    function enqueue(action, fields, kind = 'action', method = 'POST') {
        const waiter = new Promise((resolve) => {
            const last = queue[queue.length - 1];
            if (kind === 'pull-latest' && last?.kind === kind) {
                last.fields.prs.push(...fields.prs);
                last.waiters.push({ resolve });
            } else {
                queue.push({ action, fields, kind, method, waiters: [{ resolve }] });
            }
        });
        drainQueue();
        return waiter;
    }

    /**
     * Apply `patch` to a row now, send the action, revert when the server
     * rejects it. Success needs no handling: the stream delivers the
     * confirmed snapshot, and stream events landing mid-queue are dropped
     * while `busy`, so nothing can clobber a newer optimistic flip.
     */
    function optimisticRow(prNumber, patch, action, fields, method = 'POST') {
        const row = payload?.value?.prs?.find((r) => r.pr === prNumber);
        const snapshot = row ? { ...row } : null;
        if (row) Object.assign(row, typeof patch === 'function' ? patch(row) : patch);
        const waiter = enqueue(action, fields, 'action', method);
        if (snapshot) {
            waiter.then((result) => {
                if (result === false || result?.ok === false) {
                    const current = payload?.value?.prs?.find((r) => r.pr === prNumber);
                    if (current) Object.assign(current, snapshot);
                }
            });
        }
        return waiter;
    }

    function togglePr(pr) {
        const row = payload?.value?.prs?.find((r) => r.pr === pr.pr);
        const target = !effectiveActive(row ?? pr);
        // Mirror the server: staging back to the live state clears the flag.
        const patch = (r) => ({ pending_active: target === r.active ? null : target });
        return optimisticRow(pr.pr, patch, '/status/testing/prs', { prs: [pr.pr], active: target }, 'PATCH');
    }

    function updatePr(pr) {
        enqueue('/status/pull-latest', { prs: [pr.pr] }, 'pull-latest');
    }

    function removePr(pr) {
        // Not-live rows vanish on re-fetch; staged ones keep the flag.
        return optimisticRow(pr.pr, { pending_remove: true }, '/status/remove', { prs: [pr.pr] });
    }

    // Undo a staged removal: the server just clears the flag, so the row's
    // pinned commit and toggle state come back untouched.
    function restorePr(pr) {
        return optimisticRow(pr.pr, { pending_remove: false }, '/status/restore', { prs: [pr.pr] });
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

    function markRecentlyAdded(prs) {
        recentlyAdded.value = new Set([...recentlyAdded.value, ...prs]);
        setTimeout(() => {
            const remaining = new Set(recentlyAdded.value);
            prs.forEach((pr) => remaining.delete(pr));
            recentlyAdded.value = remaining;
        }, RECENT_HIGHLIGHT_MS);
    }

    async function addPrs() {
        if (adding.value) return;
        const value = addInput.value.trim();
        if (!value) return;
        const prs = parsePrNumbers(value);
        if (!prs.length) return;
        adding.value = true;
        try {
            const result = await enqueue('/status/add', { prs });
            // A failed add keeps the input so it's obvious the PR didn't land.
            if (result && result.ok) {
                addInput.value = '';
                markRecentlyAdded(prs);
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
        recentlyAdded,
        togglePr,
        updatePr,
        removePr,
        restorePr,
        deploy,
        refresh,
        addPrs
    };
}
