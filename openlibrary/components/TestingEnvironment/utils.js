/**
 * Pure logic and fetch service for the Testing Environment panel.
 *
 * The Vue component (TestingEnvironment.vue) renders from these decisions —
 * they are plain functions so the drift/pending/update logic stays unit
 * testable without mounting an SFC.
 */

import { _, fmt, ngettext } from '../../plugins/openlibrary/js/i18n.js';

export const REPO_URL = 'https://github.com/internetarchive/openlibrary';

/**
 * The panel's strings in the page language, with `%(name)s` placeholders that
 * `panelString` fills. The plurals, `changes` and `behind`, are in `panelString`.
 */
export const STRINGS = {
    loading: _('Loading testing environment…'),
    loadError: _('Could not load the testing environment.'),
    retry: _('Try again'),
    actionFailed: _('Could not complete that action.'),
    addFailedNotFound: _('PR %(num)s does not exist.'),
    addFailedUnavailable: _('Could not check PR %(num)s — GitHub is unavailable.'),
    addFailedTokenInvalid: _('Could not add PR %(num)s — GitHub API token is invalid or expired. Check `github_api_token` in config/openlibrary.yml.'),
    addFailedOther: _('Could not add PR %(num)s.'),
    title: _('Testing Environment'),
    addPrs: _('Add PRs'),
    addPlaceholder: _('PR numbers or URLs, space or comma separated'),
    add: _('Add PRs'),
    addChange: _('Add'),
    pr: _('PR'),
    draft: _('Draft'),
    author: _('Author'),
    assignee: _('Assignee'),
    drift: _('Drift'),
    next: _('Next deploy'),
    liveNow: _('Live now'),
    notLive: _('Not yet deployed'),
    mergeConflict: _('Deploy failed (merge conflict)'),
    closed: _('This PR is already closed.'),
    actions: _('Actions'),
    ok: _('OK'),
    prOnTesting: _('PR %(num)s on testing'),
    changeOnDeploy: _('changes on deploy'),
    update: _('Update'),
    updatePin: _('Update pin'),
    enable: _('Enable'),
    disable: _('Disable'),
    remove: _('Remove'),
    restore: _('Restore'),
    refresh: _('Refresh from GitHub'),
    deploy: _('Deploy'),
    nothingToDeploy: _('Nothing to deploy — testing matches the current set.'),
    mergedToMaster: _('merged to master'),
    closedWithoutMerging: _('closed without merging'),
    unknown: _('Drift unknown, pinned at %(sha)s'),
    currentCommit: _('Up-to-date, pinned at %(sha)s'),
    neverDeployed: _('Never deployed'),
    deployingStarted: _('Deploying, started %(time)s'),
    deployingStartedBy: _('Deploying, started %(time)s by %(user)s'),
    deployingStage: _('Deploying, started %(time)s — %(stage)s'),
    deployingStageBy: _('Deploying, started %(time)s — %(stage)s by %(user)s'),
    deploySucceeded: _('Deploy succeeded %(time)s'),
    deploySucceededBy: _('Deploy succeeded %(time)s by %(user)s'),
    deployFailed: _('Deploy failed %(time)s'),
    deployFailedBy: _('Deploy failed %(time)s by %(user)s'),
    deployFailedTrigger: _('Could not start the deploy — Jenkins did not accept the build.'),
    deployUnconfigured: _('Deploy is not configured on this instance — nothing was deployed.'),
    lastDeploy: _('Last deploy %(time)s'),
    lastDeployBy: _('Last deploy %(time)s by %(user)s'),
    viewJenkins: _('View Jenkins'),
    noPrs: _('No PRs in testing set.')
};

/**
 * The panel string for `key`, with its `%(name)s` placeholders filled from
 * `vars`. `changes` and `behind` pick their plural form by `vars.count`.
 */
export function panelString(key, vars = {}) {
    let template = STRINGS[key] ?? key;
    if (key === 'changes') template = ngettext('%(num)s change will be applied', '%(num)s changes will be applied', vars.count);
    if (key === 'behind') template = ngettext('%(num)s commit behind %(sha)s', '%(num)s commits behind %(sha)s', vars.count);
    return fmt(template, vars);
}

/**
 * The action endpoints answer {"ok": false, "error": "<code>"} for business
 * failures; each code maps to the string that explains it.
 */
export const ACTION_ERRORS = {
    add_failed: 'actionFailed',
    deploy_failed: 'deployFailedTrigger',
    deploy_unconfigured: 'deployUnconfigured'
};

export function parsePrNumbers(value) {
    return String(value || '')
        .trim()
        .split(/[\s,]+/)
        .filter(Boolean)
        .flatMap(token => {
            if (token.includes('/issues/')) return [];
            const match = token.match(/\/pull\/(\d+)/);
            const number = match ? Number(match[1]) : Number(token.replace(/^#/, ''));
            return Number.isInteger(number) && number > 0 ? [number] : [];
        });
}

/**
 * The toast to show for a failed action.
 *
 * An add that GitHub rejected carries `failed_prs` ({number: reason}), so it
 * can name the numbers that didn't land and why. Every other code — and an
 * add without that detail — falls back to its fixed string.
 */
export function actionErrorMessage(result) {
    const failed = result?.failed_prs;
    if (result?.error === 'add_failed' && failed && Object.keys(failed).length) {
        const reasons = {
            not_found: 'addFailedNotFound',
            unavailable: 'addFailedUnavailable',
            token_invalid: 'addFailedTokenInvalid'
        };
        // Numeric order, not insertion order: JSON object keys that look like
        // integers come back re-sorted ascending by the JS engine, so relying
        // on the server's order would show them in an order nobody chose.
        return Object.keys(failed)
            .map(Number)
            .sort((a, b) => a - b)
            .map(prNumber => panelString(reasons[failed[prNumber]] || 'addFailedOther', { num: prNumber }))
            .join(' ');
    }
    const key = ACTION_ERRORS[result?.error] || 'actionFailed';
    return panelString(key);
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
 * Send a JSON action request and resolve its JSON body.
 */
export async function postAction(action, fields = {}, method = 'POST') {
    const init = {
        method,
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
        },
        credentials: 'same-origin'
    };
    // fetch() throws if a GET or HEAD request carries a body.
    if (method !== 'GET' && method !== 'HEAD') {
        init.body = JSON.stringify(fields);
    }
    const response = await fetch(action, init);
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
    const frames = links.map(link => ({
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
    return String(value || '')
        .slice(0, 16)
        .replace('T', ' ');
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
    return pr.pending_active === undefined || pr.pending_active === null ? pr.active !== false : pr.pending_active;
}

/**
 * Whether pull-latest is offered: there is a newer commit to bring in and no
 * pull is already staged.
 */
export function canUpdate(pr) {
    return Number(pr.drift) > 0 && !pr.pull_latest_sha;
}

/**
 * Decide the drift verdict: label, optional href, and the hover title.
 * Merged PRs are filtered out before a row is rendered, so they never reach
 * this.
 */
export function driftPill(pr) {
    const pinned = String(pr.commit || '').slice(0, 7);
    const drift = Number(pr.drift);

    if (drift === 0) {
        return { label: STRINGS.ok, href: '', title: panelString('currentCommit', { sha: pinned }) };
    }
    if (drift < 0 || Number.isNaN(drift)) {
        return {
            label: '?',
            href: `${REPO_URL}/commit/${encodeURIComponent(pr.commit || '')}`,
            title: panelString('unknown', { sha: pinned })
        };
    }
    return {
        label: `-${drift}`,
        href: pr.head_sha ? `${REPO_URL}/compare/${encodeURIComponent(pr.commit || '')}...${encodeURIComponent(pr.head_sha)}` : '',
        title: panelString('behind', { count: drift, num: drift, sha: pinned })
    };
}
