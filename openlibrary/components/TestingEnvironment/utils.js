/**
 * Pure logic and fetch service for the Testing Environment panel.
 *
 * The Vue component (TestingEnvironment.vue) renders from these decisions —
 * they are plain functions so the drift/pending/update logic stays unit
 * testable without mounting an SFC.
 */

export const REPO_URL = 'https://github.com/internetarchive/openlibrary';

/**
 * English fallbacks for the translated strings passed in from the server.
 * Placeholder values are normalized to %s by the template.
 */
export const DEFAULT_STRINGS = {
    loading: 'Loading testing environment…',
    loadError: 'Could not load the testing environment.',
    retry: 'Try again',
    actionComplete: 'Action completed.',
    actionFailed: 'Could not complete that action.',
    deployTriggered: 'Deploy triggered!',
    deployFailed: 'Could not reach Jenkins — nothing was deployed. Your pending changes are still staged; try again.',
    deployUnconfigured: 'No Jenkins token is configured, so no build was started. Pending changes were cleared locally.',
    githubRefreshed: 'GitHub status refreshed.',
    title: 'Testing Environment',
    addPrs: 'Add PRs',
    addPlaceholder: 'PR numbers or URLs, space or comma separated',
    add: 'Add PRs',
    addChange: 'Add',
    on: 'On',
    pr: 'PR',
    author: 'Author',
    assignee: 'Assignee',
    drift: 'Drift',
    actions: 'Actions',
    ok: 'OK',
    prOnTesting: 'PR #%s on testing',
    changeOnDeploy: 'changes on deploy',
    removing: 'Removing #%s…',
    updating: 'Updating #%s…',
    enabling: 'Enabling #%s…',
    disabling: 'Disabling #%s…',
    deploying: 'Deploying to testing…',
    adding: 'Adding PRs…',
    update: 'Update',
    updatePin: 'Update pin',
    enable: 'Enable',
    disable: 'Disable',
    remove: 'Remove',
    refresh: 'Refresh from GitHub',
    deploy: 'Deploy',
    changeOne: '%s change will be applied',
    changeMany: '%s changes will be applied',
    nothingToDeploy: 'Nothing to deploy — testing matches the current set.',
    mergedToMaster: 'merged to master',
    unknown: 'Drift unknown, pinned at %s',
    currentCommit: 'Up-to-date, pinned at %s',
    behindOne: '%s commit behind %s',
    behindMany: '%s commits behind %s',
    neverDeployed: 'Never deployed',
    deployingStarted: 'Deploying, started %s',
    lastDeploy: 'Last deploy %s',
    viewJenkins: 'View Jenkins',
    noPrs: 'No PRs in testing set.'
};

/**
 * Replace %s placeholders in order; %% is a literal percent.
 */
export function sprintf(fmt, ...args) {
    return String(fmt).replace(/%s/g, () => (args.length ? args.shift() : '%s'));
}

/**
 * Decode a URL-encoded JSON attribute value (how render_component passes
 * dict/list attrs to Vue components).
 */
export function decodeAndParseJSON(str) {
    return JSON.parse(decodeURIComponent(str));
}

/**
 * Return the same-origin JSON endpoint for the current deployment.
 *
 * The testing site exposes FastAPI behind /_fast; local development proxies
 * the unprefixed path through web.py to the FastAPI container.
 */
export function testingStatusUrl(location) {
    return location.hostname === 'testing.openlibrary.org'
        ? '/_fast/status/testing.json'
        : '/status/testing.json';
}

/**
 * Fetch the testing-environment state.
 */
export async function getTestingStatus(location = window.location) {
    const response = await fetch(testingStatusUrl(location), {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin'
    });
    if (!response.ok) {
        throw new Error(`Testing status failed: ${response.status}`);
    }
    return response.json();
}

/**
 * POST an action and return its response. The legacy handlers redirect to
 * /status; callers intentionally discard that HTML and fetch JSON afterward.
 * Array values are repeated so web.input(prs=[]) sees multiple checkboxes.
 */
export async function postAction(action, fields = {}) {
    const body = new URLSearchParams();
    for (const [key, value] of Object.entries(fields)) {
        if (Array.isArray(value)) {
            value.forEach((item) => body.append(key, item));
        } else {
            body.append(key, value);
        }
    }

    const response = await fetch(action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'same-origin',
        body
    });
    if (!response.ok) {
        throw new Error(`${action} failed: ${response.status}`);
    }
    return response;
}

/**
 * "2026-08-06T15:00:00+00:00" → "2026-08-06 15:00"
 */
export function formatTime(value) {
    return String(value || '').slice(0, 16).replace('T', ' ');
}

/**
 * https-only, same-origin-http fallback; blocks protocol-relative junk.
 */
export function safeHttpUrl(value, origin = window.location.origin) {
    if (!value || String(value).startsWith('//')) return '';
    try {
        const url = new URL(value, origin);
        if (url.protocol === 'https:') return url.href;
        return url.protocol === 'http:' && url.origin === origin ? url.href : '';
    } catch {
        return '';
    }
}

/**
 * The state the row's toggle shows: a staged pending_active wins until the
 * next deploy applies it.
 */
export function effectiveActive(pr) {
    return pr.pending_active === undefined || pr.pending_active === null
        ? pr.active !== false
        : pr.pending_active;
}

/**
 * Whether a change is staged for the next deploy.
 */
export function isPending(pr) {
    return Boolean(pr.pull_latest_sha)
        || (pr.pending_active !== undefined && pr.pending_active !== null);
}

/**
 * Whether pull-latest is offered: there is a newer commit to bring in and no
 * pull is already staged.
 */
export function canUpdate(pr) {
    return Number(pr.drift) > 0 && !pr.pull_latest_sha;
}

/**
 * Decide the drift pill: kind ('ok' | 'unknown' | 'behind'), label, optional
 * href, and the hover title. `strings` are the translated panel strings, with
 * %s placeholders filled by sprintf. Merged PRs are filtered out before a row
 * is rendered, so they never reach this.
 */
export function driftPill(pr, strings) {
    const pinned = String(pr.commit || '').slice(0, 7);
    const drift = Number(pr.drift);
    const t = (key, ...args) => sprintf(strings[key] || key, ...args);

    if (drift === 0) {
        return { kind: 'ok', label: strings.ok, href: '', title: t('currentCommit', pinned) };
    }
    if (drift < 0 || Number.isNaN(drift)) {
        return {
            kind: 'unknown',
            label: '?',
            href: `${REPO_URL}/commit/${encodeURIComponent(pr.commit || '')}`,
            title: t('unknown', pinned)
        };
    }
    return {
        kind: 'behind',
        label: `-${drift}`,
        href: pr.head_sha
            ? `${REPO_URL}/compare/${encodeURIComponent(pr.commit || '')}...${encodeURIComponent(pr.head_sha)}`
            : '',
        title: drift === 1 ? t('behindOne', drift, pinned) : t('behindMany', drift, pinned)
    };
}

/**
 * The toast wording after an action, read off the redirect URL the handler
 * returned. Falls back to the generic confirmation for anything unexpected.
 */
export function actionResultMessage(action, responseUrl, strings) {
    try {
        const url = new URL(responseUrl, window.location.href);
        if (action.endsWith('/deploy')) {
            if (url.searchParams.has('deploy_failed')) return strings.deployFailed;
            if (url.searchParams.has('deploy_unconfigured')) return strings.deployUnconfigured;
            if (url.searchParams.has('deploy_triggered')) return strings.deployTriggered;
        }
        if (action.endsWith('/refresh')) return strings.githubRefreshed;
    } catch {
        // A malformed redirect URL falls back to the generic confirmation.
    }
    return strings.actionComplete;
}
