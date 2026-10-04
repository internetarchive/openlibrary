// Make jQuery available globally for tests
import $ from 'jquery';
window.jQuery = $;
window.$ = $;

// Improve error reporting for unhandled promise rejections.
// Under the vmThreads pool `process` is shared across test files while each
// file gets a fresh globalThis, so guard on the shared process's listeners.
if (!process.listeners('unhandledRejection').some((fn) => fn.name === 'olRethrowUnhandledRejection')) {
    process.on('unhandledRejection', function olRethrowUnhandledRejection(error) {
        throw error;
    });
}

// jsdom emits "Not implemented" jsdomErrors (canvas, scrollTo, navigation...)
// straight to the terminal via its virtual console, bypassing Vitest's console
// interception. These are expected environment limitations, not test problems,
// so filter them at the source and forward everything else.
const virtualConsole = window.jsdom?.virtualConsole;
if (virtualConsole) {
    virtualConsole.removeAllListeners('jsdomError');
    virtualConsole.on('jsdomError', (error) => {
        if (error.type === 'not-implemented') return;
        // Mirror jsdom's own forwardTo() formatting for the remaining errors.
        // eslint-disable-next-line no-console
        console.error(error.type === 'unhandled-exception' ? error.cause.stack : error.message);
    });
}
