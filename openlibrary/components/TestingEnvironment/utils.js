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
    actionFailed: 'Could not complete that action.',
    title: 'Testing Environment',
    addPrs: 'Add PRs',
    addPlaceholder: 'PR numbers or URLs, space or comma separated',
    add: 'Add PRs',
    addChange: 'Add',
    pr: 'PR',
    author: 'Author',
    assignee: 'Assignee',
    drift: 'Drift',
    next: 'Next deploy',
    liveNow: 'Live now',
    notLive: 'Not yet deployed',
    mergeConflict: 'Deploy failed (merge conflict)',
    closed: 'This PR is already closed.',
    actions: 'Actions',
    ok: 'OK',
    prOnTesting: 'PR #%s on testing',
    changeOnDeploy: 'changes on deploy',
    update: 'Update',
    updatePin: 'Update pin',
    enable: 'Enable',
    disable: 'Disable',
    remove: 'Remove',
    restore: 'Restore',
    refresh: 'Refresh from GitHub',
    deploy: 'Deploy',
    changeOne: '%s change will be applied',
    changeMany: '%s changes will be applied',
    nothingToDeploy: 'Nothing to deploy — testing matches the current set.',
    mergedToMaster: 'merged to master',
    closedWithoutMerging: 'closed without merging',
    unknown: 'Drift unknown, pinned at %s',
    currentCommit: 'Up-to-date, pinned at %s',
    behindOne: '%s commit behind %s',
    behindMany: '%s commits behind %s',
    neverDeployed: 'Never deployed',
    deployingStarted: 'Deploying, started %s',
    deployingStartedBy: 'Deploying, started %s by %s',
    deployingStage: 'Deploying, started %s — %s',
    deployingStageBy: 'Deploying, started %s — %s by %s',
    deploySucceeded: 'Deploy succeeded %s',
    deploySucceededBy: 'Deploy succeeded %s by %s',
    deployFailed: 'Deploy failed %s',
    deployFailedBy: 'Deploy failed %s by %s',
    deployFailedTrigger: 'Could not start the deploy — Jenkins did not accept the build.',
    deployUnconfigured: 'Deploy is not configured on this instance — nothing was deployed.',
    lastDeploy: 'Last deploy %s',
    lastDeployBy: 'Last deploy %s by %s',
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
 * Fetch the testing-environment state.
 */
export async function getTestingStatus() {
    const response = await fetch('/status/testing.json', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin'
    });
    if (!response.ok) {
        throw new Error(`Testing status failed: ${response.status}`);
    }
    return response.json();
}

/**
 * POST an action and resolve its JSON body. The status handlers answer
 * {"ok": true} or {"ok": false, "error": "<code>"} directly — no redirect to
 * re-fetch — so callers toast on ok=false and then reload the panel state
 * from /status/testing.json. Array values are repeated so
 * web.input(prs=[]) sees multiple checkboxes.
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
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json'
        },
        credentials: 'same-origin',
        body
    });
    if (!response.ok) {
        throw new Error(`${action} failed: ${response.status}`);
    }
    return response.json();
}

// The deploy badge: a vivid orange wedge covering the top-right half of the
// favicon, so it is unmistakable at tab-strip size. Bright enough to read on
// the paper and green tiles, and brighter than the testing tile itself so it
// still stands out there.
const FAVICON_BADGE_COLOR = 'hsl(24, 100%, 50%)';

/**
 * Which environment a favicon href belongs to: 'production', 'development',
 * or 'testing'. Null for anything that isn't one of our openlibrary
 * favicons, so foreign favicon links are left alone.
 */
export function faviconEnv(href) {
    const value = String(href || '');
    if (!/openlibrary(?:-[a-z]+)?-\d+x\d+\.png$/.test(value)) return null;
    if (value.includes('-testing-')) return 'testing';
    if (value.includes('-development-')) return 'development';
    return 'production';
}

// A deploy is a few minutes at most. If the tab is frozen or heavily
// throttled in the background, the poll that would remove the badge can't
// run — but browsers fire an overdue timer the instant the tab unfreezes, so
// this removes the badge immediately on return instead of waiting for the
// next poll (which re-applies it if the deploy is genuinely still running).
const FAVICON_MAX_DURATION_MS = 20 * 60 * 1000;

/**
 * Mark the page favicon while a deploy runs: draw the real favicon PNG with
 * a static badge wedge once and swap the link hrefs to the result; restore the
 * original hrefs on stop. A static mark — instead of an animated spinner —
 * costs one canvas render at start and one href swap at the end: no
 * animation loop, so there is nothing to lag on a busy main thread and no
 * per-frame favicon repaint for the browser to throttle. Only the given
 * rel="icon" links are touched; a failsafe removes the badge even when the
 * poll that normally ends it can't run in a hidden tab.
 */
export function applyDeployBadge(links) {
    const frames = links.map((link) => ({
        link,
        original: link.getAttribute('href'),
        image: new Image(),
        canvas: document.createElement('canvas')
    }));
    let loaded = 0;
    let stopped = false;
    let failsafe = null;

    function stop() {
        if (stopped) return;
        stopped = true;
        clearTimeout(failsafe);
        frames.forEach(({ link, original }) => link.setAttribute('href', original));
    }

    function drawBadge() {
        for (const { link, image, canvas } of frames) {
            const ctx = canvas.getContext('2d');
            if (!ctx) continue;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
            // Badge wedge: the top-right half of the tile, split along the
            // main diagonal (top-left to bottom-right).
            ctx.beginPath();
            ctx.fillStyle = FAVICON_BADGE_COLOR;
            ctx.moveTo(0, 0);
            ctx.lineTo(canvas.width, 0);
            ctx.lineTo(canvas.width, canvas.height);
            ctx.closePath();
            ctx.fill();
            link.setAttribute('href', canvas.toDataURL('image/png'));
        }
    }

    frames.forEach(({ link, image, canvas }) => {
        image.onload = () => {
            if (stopped) return;
            canvas.width = image.naturalWidth;
            canvas.height = image.naturalHeight;
            loaded += 1;
            // Wait for every favicon so the badge appears on all of them at once.
            if (loaded === frames.length) {
                drawBadge();
            }
        };
        image.onerror = () => {
            // A broken image means nothing to draw — restore and give up.
            stop();
        };
        image.src = link.getAttribute('href');
    });

    failsafe = setTimeout(stop, FAVICON_MAX_DURATION_MS);
    return stop;
}

/**
 * "2026-08-06T15:00:00+00:00" → "2026-08-06 15:00"
 */
export function formatTime(value) {
    return String(value || '').slice(0, 16).replace('T', ' ');
}

/**
 * Relative "X ago" label for an ISO timestamp, in the browser's locale.
 * Empty for invalid/empty input. ``now`` is injectable so a caller can tick
 * the label forward without changing the underlying payload (Date.now() by
 * default); the exact time rides in the title attribute.
 */
export function timeAgo(value, now = Date.now()) {
    const date = new Date(value);
    if (!value || Number.isNaN(date.getTime())) return '';
    const seconds = Math.round((date.getTime() - now) / 1000);
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
    const abs = Math.abs(seconds);
    if (abs < 60) return rtf.format(seconds, 'second');
    if (abs < 3600) return rtf.format(Math.round(seconds / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(seconds / 3600), 'hour');
    return rtf.format(Math.round(seconds / 86400), 'day');
}

/**
 * The state the next deploy leaves the row in — what the switch displays and
 * what a click moves away from. The server emits `pending_active` only when a
 * toggle is staged (and differs from `active`), so its presence is the staged
 * direction; when nothing is staged the current `active` state stands.
 * Clicking again after staging undoes the change.
 */
export function effectiveActive(pr) {
    return pr.pending_active === undefined || pr.pending_active === null
        ? pr.active !== false
        : pr.pending_active;
}

/**
 * Whether pull-latest is offered: there is a newer commit to bring in and no
 * pull is already staged.
 */
export function canUpdate(pr) {
    return Number(pr.drift) > 0 && !pr.pull_latest_sha;
}

/**
 * Decide the drift verdict: label, optional href, and the hover title. `strings`
 * are the translated panel strings, with %s placeholders filled by sprintf.
 * Merged PRs are filtered out before a row is rendered, so they never reach
 * this.
 */
export function driftPill(pr, strings) {
    const pinned = String(pr.commit || '').slice(0, 7);
    const drift = Number(pr.drift);
    const t = (key, ...args) => sprintf(strings[key] || key, ...args);

    if (drift === 0) {
        return { label: strings.ok, href: '', title: t('currentCommit', pinned) };
    }
    if (drift < 0 || Number.isNaN(drift)) {
        return {
            label: '?',
            href: `${REPO_URL}/commit/${encodeURIComponent(pr.commit || '')}`,
            title: t('unknown', pinned)
        };
    }
    return {
        label: `-${drift}`,
        href: pr.head_sha
            ? `${REPO_URL}/compare/${encodeURIComponent(pr.commit || '')}...${encodeURIComponent(pr.head_sha)}`
            : '',
        title: drift === 1 ? t('behindOne', drift, pinned) : t('behindMany', drift, pinned)
    };
}
