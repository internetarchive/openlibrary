import { ref, shallowRef, onMounted, onBeforeUnmount } from 'vue';
import { getTestingStatus } from '../utils.js';
import { useLocalStorage } from '../../composables/useLocalStorage.js';

const CACHE_KEY = 'openlibrary:testing-environment-status';

/**
 * Fetches, caches, and periodically refreshes the testing-environment
 * state from the server.  The 1 s interval bumps `now` every tick (so
 * relative labels advance) and only hits the network every 5th tick.
 *
 * @param {import('vue').ShallowRef<boolean>} busy — action queue state shared with useActions
 * @returns {{
 *   view:   import('vue').ShallowRef<string>,
 *   payload: import('vue').ShallowRef<object|null>,
 *   now:    import('vue').ShallowRef<number>,
 *   loadStatus: (showLoading?: boolean, renderError?: boolean, manageBusy?: boolean) => Promise<boolean>,
 *   retry: () => void,
 * }}
 */
export function useTestingStatus(busy) {
    const { value: payload, setValue: setCachedPayload } = useLocalStorage(CACHE_KEY);
    const initialPayload = payload.value;
    const view = ref(initialPayload ? 'ready' : 'loading'); // 'loading' | 'error' | 'ready'
    const now = shallowRef(Date.now());

    let timer = null;

    // ── Core fetch ───────────────────────────────────────────────────
    async function loadStatus(showLoading = false, renderError = true, manageBusy = true) {
        if (manageBusy) busy.value = true;
        if (showLoading && !payload.value) view.value = 'loading';
        try {
            const newPayload = await getTestingStatus();
            // Skip the assignment when nothing changed — a fresh object
            // identity would repaint the panel (the flash on tab return).
            if (!payload.value || JSON.stringify(newPayload) !== JSON.stringify(payload.value)) {
                setCachedPayload(newPayload);
            }
            view.value = 'ready';
            return true;
        } catch {
            if (renderError && !payload.value) view.value = 'error';
            return false;
        } finally {
            if (manageBusy) busy.value = false;
        }
    }

    // Re-fetch quietly: no loading view, no error takeover, no busy flag.
    // Skipped while an action is in flight.
    function silentRefresh() {
        if (busy.value) return;
        loadStatus(false, false, false);
    }

    function onVisibilityChange() {
        if (document.visibilityState === 'visible') {
            now.value = Date.now();
            silentRefresh();
        }
    }

    function retry() {
        loadStatus(true);
    }

    // ── Lifecycle ────────────────────────────────────────────────────
    onMounted(() => {
        loadStatus();
        // Single 1 s interval: bumps `now` every tick (advances the
        // label, no network), and refreshes data only on a tick at a
        // :05 clock boundary.
        timer = setInterval(() => {
            now.value = Date.now();
            if (Math.floor(now.value / 1000) % 5 === 0) {
                silentRefresh();
            }
        }, 1000);
        document.addEventListener('visibilitychange', onVisibilityChange);
    });

    onBeforeUnmount(() => {
        clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });

    return { view, payload, now, loadStatus, retry };
}
