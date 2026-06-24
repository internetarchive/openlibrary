import * as Sentry from '@sentry/browser';

export default function initSentry() {
    const config = window.OL_SENTRY;
    if (!config || !config.dsn) return;

    Sentry.init({
        dsn: config.dsn,
        environment: config.environment,
        release: config.release,
        sampleRate: config.sampleRate,
        tracesSampleRate: config.tracesSampleRate,
        integrations: [
            Sentry.browserTracingIntegration({
                // Use the server's normalised route name (e.g. "/type/edition") so browser
                // pageload spans group the same way as the server-side transactions.
                beforeStartSpan: (options) => ({
                    ...options,
                    name: config.transactionName ?? options.name,
                }),
            }),
        ],
        // Performance monitoring only — drop all error events
        beforeSend: () => null,
        // Inject sentry-trace/baggage headers on same-origin requests for distributed tracing
        tracePropagationTargets: [/^\//],
    });
}
