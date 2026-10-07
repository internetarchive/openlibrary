import { ref, shallowRef } from 'vue';
import { actionErrorMessage, effectiveActive, parsePrNumbers, postAction } from '../utils.js';

// How long a newly added row stays highlighted. Purely client-side: a page
// refresh clears it, which is the intended behaviour.
const RECENT_HIGHLIGHT_MS = 10000;

/**
 * PR toggle, update, remove, restore, deploy, refresh, and add actions.
 *
 * Clicks flip their row instantly; the queue sends POSTs in order and the
 * last response of a drain carries the staged flags, which are copied over
 * the rows. Earlier responses predate still-queued requests, so only the
 * last one is applied — anything without rows (deploy, refresh, add,
 * pull-latest) confirms via the stream instead.
 *
 * @param {object}  opts
 * @param {import('vue').ShallowRef<boolean>} opts.busy       — whether the action queue is processing
 * @param {import('vue').Ref<object|null>} opts.payload       — server snapshot rows (mutated optimistically, confirmed at drain end)
 * @param {Function} opts.setToast   — show an error toast
 * @param {object}  opts.strings     — translated strings (plain object, set once at setup)
 * @returns {object} action flags and methods
 */
export function useActions({ busy, payload, setToast, strings }) {
    const refreshing = shallowRef(false);
    const adding = shallowRef(false);
    const deploying = shallowRef(false);
    const addInput = shallowRef('');
    // PRs with a pull-latest request in flight. Plain numbers, so direct
    // add/delete on a ref-wrapped Set stays reactive (no copy dance needed).
    const updating = ref(new Set());
    // PR numbers added within the last RECENT_HIGHLIGHT_MS. Replaced rather
    // than mutated, because shallowRef does not track changes inside a Set.
    const recentlyAdded = shallowRef(new Set());
    const queue = [];
    let draining = false;

    function text(key, ...args) {
        const fmt = strings[key] || key;
        return String(fmt).replace(/%s/g, () => (args.length ? args.shift() : '%s'));
    }

    // No re-fetch here: toggle/remove/restore responses carry the staged
    // rows, and the drain applies only the last one; anything else confirms
    // via the stream (polling covers a dead stream).
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
                // Only the last response of a drain is applied: it was
                // computed from state including every queued save, so it is
                // the truth. Earlier ones predate queued requests and would
                // clobber their optimistic flips (the rapid-toggle flicker).
                if (!queue.length) applyConfirmedState(result);
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

    // ── Optimistic rows, confirmed at drain end ───────────────────────
    // Copy the staged flags from a mutation response over our rows, and drop
    // rows the server removed outright (never-deployed deletes have nothing
    // to stage — without this they linger with a dead undo button). Merges
    // flags only otherwise — never adds rows — so a partial or empty
    // response is always safe to apply or skip.
    function applyConfirmedState(result) {
        const current = payload?.value?.prs;
        if (!Array.isArray(current)) return;
        for (const pr of result?.removed_prs ?? []) {
            const index = current.findIndex((r) => r.pr === pr);
            if (index !== -1) current.splice(index, 1);
        }
        const rows = result?.prs;
        if (!Array.isArray(rows)) return;
        for (const update of rows) {
            const row = current.find((r) => r.pr === update.pr);
            if (row) {
                row.pending_active = update.pending_active ?? null;
                row.pending_remove = update.pending_remove ?? false;
            }
        }
    }

    // Flip a row instantly and send the action; a rejected send restores the
    // snapshot. (A same-row rapid re-toggle supersedes the snapshot, and the
    // drain-end apply corrects it — transient by construction.)
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
        updating.value.add(pr.pr);
        const waiter = enqueue('/status/pull-latest', { prs: [pr.pr] }, 'pull-latest');
        waiter.then(() => updating.value.delete(pr.pr));
        return waiter;
    }

    function removePr(pr) {
        // Not-live rows vanish on confirm; staged ones keep the flag.
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
        updating,
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
