import { ref, shallowRef, onMounted, onBeforeUnmount } from 'vue';
import { getTestingStatus } from '../utils.js';
import { useLocalStorage } from '../../composables/useLocalStorage.js';
import { useEventStream } from './useEventStream.js';

const CACHE_KEY = 'openlibrary:testing-environment-status';
const STREAM_URL = '/status/testing/stream';
const FALLBACK_POLL_SECONDS = 5;

/**
 * Panel state for the testing environment: fetches, caches, and
 * live-refreshes the payload, with `now` ticking the relative labels.
 *
 * Updates arrive through `useEventStream` (the push path). While that
 * stream is refused or mid-retry, `streaming` stays false and the 1 s
 * ticker refreshes data on :05 boundaries — the panel's original polling
 * behavior, which is the worst case this design can degrade to.
 *
 * Pushes and polls pause while the action queue drains: a snapshot sampled
 * between two queued saves predates the later ones, and applying it would
 * clobber their optimistic flips. The drain-end response reconciles
 * everything instead.
 *
 * @param {import('vue').ShallowRef<boolean>} busy — action queue state shared with useActions
 * @returns {{
 *   view:   import('vue').Ref<string>,
 *   payload: import('vue').Ref<object|null>,
 *   now:    import('vue').ShallowRef<number>,
 *   retry: () => void,
 * }}
 */
export function useTestingStatus(busy) {
    const { value: payload, setValue: setCachedPayload } = useLocalStorage(CACHE_KEY);
    const initialPayload = payload.value;
    const view = ref(initialPayload ? 'ready' : 'loading'); // 'loading' | 'error' | 'ready'
    const now = shallowRef(Date.now());

    const { streaming } = useEventStream(STREAM_URL, {
        event: 'status',
        onPayload(streamed) {
            // Dropped while the queue drains; the drain-end response is the
            // confirmation for everything queued.
            if (busy.value) return;
            applyPayload(streamed);
        }
    });

    let timer = null;

    // ── Core state application ────────────────────────────────────────
    function applyPayload(newPayload) {
        // Skip the assignment when nothing changed — a fresh object
        // identity would repaint the panel (the flash on tab return).
        if (!payload.value || JSON.stringify(newPayload) !== JSON.stringify(payload.value)) {
            setCachedPayload(newPayload);
        }
        view.value = 'ready';
    }

    async function loadStatus(showLoading = false, renderError = true) {
        if (showLoading && !payload.value) view.value = 'loading';
        try {
            applyPayload(await getTestingStatus());
            return true;
        } catch {
            if (renderError && !payload.value) view.value = 'error';
            return false;
        }
    }

    // Re-fetch quietly: no loading view, no error takeover.
    // Skipped while the queue drains, for the same reason as pushes.
    function silentRefresh() {
        if (busy.value) return;
        loadStatus(false, false);
    }

    function onVisibilityChange() {
        if (document.visibilityState !== 'visible') return;
        // One immediate re-sync on return: `streaming` is still false at
        // this instant — the reconnecting stream opens asynchronously — so
        // this fetch always runs here, and applyPayload dedupes it against
        // the stream's own first frame.
        now.value = Date.now();
        silentRefresh();
    }

    function retry() {
        loadStatus(true);
    }

    // ── Lifecycle ─────────────────────────────────────────────────────
    onMounted(() => {
        loadStatus();
        // Single 1 s interval: bumps `now` every tick (advances the label,
        // no network), and refreshes data on a tick at a :05 clock boundary
        // only while the stream is not delivering.
        timer = setInterval(() => {
            now.value = Date.now();
            if (!streaming.value && Math.floor(now.value / 1000) % FALLBACK_POLL_SECONDS === 0) {
                silentRefresh();
            }
        }, 1000);
        document.addEventListener('visibilitychange', onVisibilityChange);
    });

    onBeforeUnmount(() => {
        clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });

    return { view, payload, now, retry };
}
