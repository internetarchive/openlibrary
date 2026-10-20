import { onBeforeUnmount, onMounted, shallowRef } from 'vue';

/**
 * Server-Sent Events lifecycle for one panel: connect, deliver, fall back.
 *
 * The stream is the panel's push path. Browsers retry transient failures
 * themselves (readyState CONNECTING); CLOSED means the server refused the
 * stream — auth loss, no endpoint — and recreating that EventSource is
 * pointless, so it is closed and `streaming` stays false for the life of
 * the mount (until the next tab return, which gives a refused stream one
 * more chance). Hidden tabs close the stream: browsers do not throttle
 * EventSource like they throttle timers, and closing lets the caller's
 * polling fallback stand in.
 *
 * @param {string} url — the stream endpoint
 * @param {object} opts
 * @param {string} opts.event — the SSE event name to listen for
 * @param {(payload: object) => void} opts.onPayload — receives each parsed
 *   event payload; a malformed frame is dropped, never passed on
 * @returns {{ streaming: import('vue').ShallowRef<boolean> }} — true whenever
 *   the pipe is demonstrably working; the caller gates its own fallback
 *   polling on it
 */
export function useEventStream(url, { event, onPayload }) {
    const streaming = shallowRef(false);
    let stream = null;

    function onStreamEvent(evt) {
        streaming.value = true;
        try {
            onPayload(JSON.parse(evt.data));
        } catch {
            // A malformed frame is dropped; the next event or poll re-syncs.
        }
    }

    function close() {
        streaming.value = false;
        if (stream) {
            stream.close();
            stream = null;
        }
    }

    function connect() {
        if (typeof EventSource === 'undefined') return; // stay on fallback polling
        stream = new EventSource(url);
        stream.addEventListener(event, onStreamEvent);
        stream.onopen = () => {
            streaming.value = true;
        };
        stream.onerror = () => {
            streaming.value = false;
            if (stream && stream.readyState === EventSource.CLOSED) {
                close();
            }
        };
    }

    function onVisibilityChange() {
        if (document.visibilityState === 'hidden') {
            close();
        } else {
            connect();
        }
    }

    onMounted(() => {
        connect();
        document.addEventListener('visibilitychange', onVisibilityChange);
    });

    onBeforeUnmount(() => {
        close();
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });

    return { streaming };
}
