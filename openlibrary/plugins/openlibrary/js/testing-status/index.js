import { getTestingStatus, postAction } from './TestingStatusService';
import { sprintf } from '../i18n.js';

const REPO_URL = 'https://github.com/internetarchive/openlibrary';

/**
 * English fallbacks for the translated strings embedded in the page shell.
 * Placeholder values are normalized to %s by the server template.
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
    merged: 'merged',
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

const FOCUS_ATTRS = ['data-row-toggle', 'data-row-action', 'data-deploy', 'data-refresh'];

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function stringsFromElement(el) {
    try {
        const raw = el.dataset.i18n;
        if (raw) return { ...DEFAULT_STRINGS, ...JSON.parse(raw) };
    } catch {
        // A malformed translation payload falls back to English.
    }
    return DEFAULT_STRINGS;
}

function formatTime(value) {
    return String(value || '').slice(0, 16).replace('T', ' ');
}

function safeHttpUrl(value) {
    if (!value || String(value).startsWith('//')) return '';
    try {
        const url = new URL(value, window.location.origin);
        if (url.protocol === 'https:') return url.href;
        return url.protocol === 'http:' && url.origin === window.location.origin ? url.href : '';
    } catch {
        return '';
    }
}

function person(name, avatar) {
    if (!name) return '<span class="testing-env__empty">—</span>';
    const avatarUrl = safeHttpUrl(avatar);
    const label = escapeHtml(name);
    // The cell is the picture alone — the username rides in title (hover) and
    // alt/aria-label (screen readers). A letter tile stands in when the API
    // has no avatar URL so the column stays pictures-only.
    const image = avatarUrl
        ? `<img class="testing-env__avatar" src="${escapeHtml(avatarUrl)}&amp;s=40" width="24" height="24" alt="${label}" title="${label}" loading="lazy">`
        : `<span class="testing-env__avatar testing-env__avatar--fallback" role="img" aria-label="${label}" title="${label}">${escapeHtml(name.charAt(0).toUpperCase())}</span>`;
    return `<span class="testing-env__person">${image}</span>`;
}

function focusedSelector(root) {
    const active = document.activeElement;
    if (!active || !root.contains(active)) return null;

    const attr = FOCUS_ATTRS.find((name) => active.hasAttribute(name));
    if (!attr) return null;
    if (active.dataset.pr) return `[${attr}][data-pr="${active.dataset.pr}"]`;

    const action = active.getAttribute('formaction');
    return action ? `[${attr}][formaction="${action}"]` : `[${attr}]`;
}

class TestingStatusPanel {
    constructor(root) {
        this.root = root;
        this.strings = stringsFromElement(root);
        this.busy = true;
        this.bind();
        this.bindFocusRefresh();
        this.setBusy(true);
        this.loadStatus();
    }

    text(key, ...args) {
        return sprintf(this.strings[key] || DEFAULT_STRINGS[key] || key, ...args);
    }

    setToast(message) {
        const toast = this.root.querySelector('[data-toast]');
        if (!toast) return;
        toast.textContent = message;
        toast.hidden = !message;
    }

    setBusy(busy) {
        this.busy = busy;
        this.root.setAttribute('aria-busy', busy ? 'true' : 'false');
        this.root.querySelectorAll('button').forEach((button) => {
            if (busy) {
                button.dataset.statusDisabled = button.disabled ? 'true' : 'false';
                button.disabled = true;
            } else if (button.dataset.statusDisabled !== undefined) {
                button.disabled = button.dataset.statusDisabled === 'true';
                delete button.dataset.statusDisabled;
            }
        });
    }

    renderLoading() {
        this.root.innerHTML = `
            <div class="testing-env__main">
                <p class="testing-env__blank" data-testing-loading role="status" aria-live="polite">${escapeHtml(this.strings.loading)}</p>
            </div>`;
    }

    renderError() {
        this.root.innerHTML = `
            <div class="testing-env__main">
                <div class="testing-env__blank" role="alert">
                    <p>${escapeHtml(this.strings.loadError)}</p>
                    <button type="button" class="testing-env__btn testing-env__btn--small" data-retry>
                        ${escapeHtml(this.strings.retry)}
                    </button>
                </div>
            </div>`;
    }

    renderPersonColumn(value, avatar) {
        return `<td class="testing-env__col-person">${person(value, avatar)}</td>`;
    }

    renderDrift(pr, isMaintainer) {
        const pinned = String(pr.commit || '').slice(0, 7);
        const merged = pr.merged === true;
        const drift = Number(pr.drift);
        let pill;

        if (merged) {
            pill = `<span class="testing-env__pill testing-env__pill--merged" title="${escapeHtml(this.text('mergedToMaster'))}">${escapeHtml(this.strings.merged)}</span>`;
        } else if (drift === 0) {
            pill = `<span class="testing-env__pill testing-env__pill--ok" title="${escapeHtml(this.text('currentCommit', pinned))}">${escapeHtml(this.strings.ok)}</span>`;
        } else if (drift < 0 || Number.isNaN(drift)) {
            const href = `${REPO_URL}/commit/${encodeURIComponent(pr.commit || '')}`;
            pill = `<a class="testing-env__pill testing-env__pill--unknown" href="${escapeHtml(href)}" title="${escapeHtml(this.text('unknown', pinned))}">?</a>`;
        } else {
            const behindText = drift === 1
                ? this.text('behindOne', drift, pinned)
                : this.text('behindMany', drift, pinned);
            const headSha = pr.head_sha ? encodeURIComponent(pr.head_sha) : '';
            const compareUrl = `${REPO_URL}/compare/${encodeURIComponent(pr.commit || '')}...${headSha}`;
            const pillContent = `-${escapeHtml(drift)}`;
            pill = pr.head_sha
                ? `<a class="testing-env__pill testing-env__pill--behind" href="${escapeHtml(compareUrl)}" title="${escapeHtml(behindText)}">${pillContent}</a>`
                : `<span class="testing-env__pill testing-env__pill--behind" title="${escapeHtml(behindText)}">${pillContent}</span>`;
        }

        // Pull-latest lives here, beside the drift it resolves: an arrow when
        // there's a newer commit to bring in, the hourglass when one is already
        // pending — the two never crowd each other.
        const prNumber = escapeHtml(pr.pr);
        const updateButton = isMaintainer && Number(pr.drift) > 0 && !pr.pull_latest_sha
            ? `<button type="submit" class="testing-env__row-action" form="testing-row-form"
                       formaction="/status/pull-latest" name="prs" value="${prNumber}" data-row-action data-pr="${prNumber}"
                       title="${escapeHtml(this.strings.update)}" aria-label="${escapeHtml(this.strings.update)}">
                    <svg class="testing-env__btn-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <line x1="12" y1="19" x2="12" y2="5" />
                        <polyline points="5 12 12 5 19 12" />
                    </svg>
                </button>`
            : '';
        const pendingActive = pr.pending_active;
        const hasPendingToggle = pendingActive !== undefined && pendingActive !== null;
        const pending = merged || Boolean(pr.pull_latest_sha) || hasPendingToggle;
        const pendingNote = pending
            ? `<span class="testing-env__pending" role="img"
                   title="${escapeHtml(this.text('changeOnDeploy'))}" aria-label="${escapeHtml(this.text('changeOnDeploy'))}">⏳</span>`
            : '';
        return `<td class="testing-env__drift-cell">
            <div class="testing-env__cell-stack">${pill}${updateButton}${pendingNote}</div>
        </td>`;
    }

    renderRow(pr, isMaintainer) {
        const merged = pr.merged === true;
        const active = pr.active !== false;
        const pendingActive = pr.pending_active;
        const effectiveActive = pendingActive === undefined || pendingActive === null
            ? active
            : pendingActive;
        const pending = merged || Boolean(pr.pull_latest_sha) || (pendingActive !== undefined && pendingActive !== null);
        const classes = [
            'testing-env__row',
            merged ? 'is-merged' : '',
            !active ? 'is-inactive' : '',
            pr.is_new ? 'is-new' : '',
            pending ? 'is-pending' : ''
        ].filter(Boolean).join(' ');
        const prNumber = escapeHtml(pr.pr);
        const prUrl = `${REPO_URL}/pull/${encodeURIComponent(pr.pr)}`;
        const title = escapeHtml(pr.title);
        const controls = isMaintainer
            ? `<td class="testing-env__col-toggle">
                    <button type="submit" class="testing-env__switch" form="testing-row-form"
                            formaction="/status/${effectiveActive ? 'disable' : 'enable'}" name="prs" value="${prNumber}"
                            data-row-toggle data-pr="${prNumber}" aria-pressed="${effectiveActive ? 'true' : 'false'}"
                            aria-label="${escapeHtml(this.text('prOnTesting', pr.pr))}">
                        <span class="testing-env__switch-knob" aria-hidden="true"></span>
                    </button>
               </td>`
            : '';
        let action = '';
        if (isMaintainer) {
            action += `<button type="submit" class="testing-env__row-action testing-env__row-action--danger" form="testing-row-form"
                        formaction="/status/remove" name="prs" value="${prNumber}" data-row-action data-pr="${prNumber}"
                        title="${escapeHtml(this.strings.remove)}" aria-label="${escapeHtml(this.strings.remove)}">
                        <svg class="testing-env__btn-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            <line x1="10" y1="11" x2="10" y2="17" />
                            <line x1="14" y1="11" x2="14" y2="17" />
                        </svg>
                    </button>`;
        }

        return `<tr data-pr="${prNumber}" class="${classes}">
            ${controls}
            <td class="testing-env__pr-cell">
                <div class="testing-env__pr-line">
                    <a class="testing-env__pr-num" href="${prUrl}">#${prNumber}</a>
                    <a class="testing-env__pr-title" href="${prUrl}" title="${title}">${title}</a>
                </div>
            </td>
            ${this.renderPersonColumn(pr.author, pr.author_avatar)}
            ${this.renderPersonColumn(pr.assignee, pr.assignee_avatar)}
            ${this.renderDrift(pr, isMaintainer)}
            ${isMaintainer ? `<td class="testing-env__col-actions">${action}</td>` : ''}
        </tr>`;
    }

    renderChange(change) {
        const labels = {
            add: this.strings.addChange,
            pin: this.text('updatePin'),
            enable: this.strings.enable,
            disable: this.strings.disable,
            remove: this.strings.remove
        };
        const detail = change.reason === 'merged'
            ? `<span class="testing-env__change-detail">${escapeHtml(this.strings.mergedToMaster)}</span>`
            : change.detail
                ? `<span class="testing-env__change-detail testing-env__change-detail--sha">${escapeHtml(change.detail)}</span>`
                : '';
        return `<li class="testing-env__change testing-env__change--${escapeHtml(change.kind)}">
            <span class="testing-env__change-kind">${escapeHtml(labels[change.kind] || change.kind)}</span>
            <a class="testing-env__change-pr" href="${REPO_URL}/pull/${encodeURIComponent(change.pr)}">#${escapeHtml(change.pr)}</a>
            <span class="testing-env__change-title">${escapeHtml(change.title)}</span>
            ${detail}
        </li>`;
    }

    renderDeploy(payload, isMaintainer) {
        const changes = payload.pending_changes || [];
        const changeCount = changes.length;
        const plan = changeCount
            ? `<p class="testing-env__plan-head">${escapeHtml(changeCount === 1
                ? this.text('changeOne', changeCount)
                : this.text('changeMany', changeCount))}</p>
               <ul class="testing-env__plan-list">${changes.map((change) => this.renderChange(change)).join('')}</ul>`
            : `<p class="testing-env__plan-empty">${escapeHtml(this.strings.nothingToDeploy)}</p>`;
        const jenkinsUrl = safeHttpUrl(this.root.dataset.jenkinsUrl);
        const deployButton = isMaintainer
            ? `<form method="post" action="/status/deploy" class="testing-env__deploy-action">
                   <button type="submit" class="testing-env__btn testing-env__btn--primary" formaction="/status/deploy"
                           data-deploy ${changeCount ? '' : 'disabled'}>
                       <svg class="testing-env__btn-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                           <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
                           <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09" />
                           <path d="M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z" />
                           <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05" />
                       </svg>
                       ${escapeHtml(this.strings.deploy)}
                   </button>
                   <button type="submit" class="testing-env__btn" formaction="/status/refresh" data-refresh>
                       <svg class="testing-env__btn-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                           <polyline points="23 4 23 10 17 10" />
                           <polyline points="1 20 1 14 7 14" />
                           <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                       </svg>
                       ${escapeHtml(this.strings.refresh)}
                   </button>
               </form>`
            : '';
        let status;
        if (payload.deploying) {
            status = `<span class="testing-env__status testing-env__status--deploying"><span class="testing-env__dot" aria-hidden="true"></span>
                ${escapeHtml(this.text('deployingStarted', formatTime(payload.deploy_started_at)))}</span>`;
        } else if (payload.last_deploy_at) {
            status = `<span class="testing-env__status"><span class="testing-env__dot" aria-hidden="true"></span>
                ${escapeHtml(this.text('lastDeploy', formatTime(payload.last_deploy_at)))}</span>`;
        } else {
            status = `<span class="testing-env__status testing-env__status--idle">${escapeHtml(this.strings.neverDeployed)}</span>`;
        }
        const jenkinsLink = jenkinsUrl
            ? `<a class="testing-env__jenkins" href="${escapeHtml(jenkinsUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(this.strings.viewJenkins)}</a>`
            : '';
        return `<section class="testing-env__deploy">
            ${deployButton}
            <div class="testing-env__plan">${plan}</div>
            <div class="testing-env__deploy-state">${status}${jenkinsLink}</div>
        </section>`;
    }

    renderPayload(payload) {
        const isMaintainer = this.root.dataset.maintainer === 'true';
        const prs = payload.prs || [];
        const addForm = isMaintainer
            ? `<form method="post" action="/status/add" class="testing-env__add" data-add-form>
                   <label class="shift" for="testing-env-add">${escapeHtml(this.strings.addPrs)}</label>
                   <input id="testing-env-add" type="text" name="pr" class="testing-env__input" autocomplete="off"
                          placeholder="${escapeHtml(this.strings.addPlaceholder)}">
                   <button type="submit" class="testing-env__btn testing-env__btn--primary">${escapeHtml(this.strings.add)}</button>
               </form>`
            : '';
        const table = prs.length
            ? `<div class="testing-env__table-wrap">
                   <table class="testing-env__table">
                   <thead><tr>
                       ${isMaintainer ? `<th scope="col">${escapeHtml(this.strings.on)}</th>` : ''}
                       <th scope="col">${escapeHtml(this.strings.pr)}</th>
                           <th scope="col">${escapeHtml(this.strings.author)}</th>
                           <th scope="col">${escapeHtml(this.strings.assignee)}</th>
                           <th scope="col">${escapeHtml(this.strings.drift)}</th>
                           ${isMaintainer ? `<th scope="col" class="testing-env__col-actions"><span class="shift">${escapeHtml(this.strings.actions)}</span></th>` : ''}
                       </tr></thead>
                       <tbody>${prs.map((pr) => this.renderRow(pr, isMaintainer)).join('')}</tbody>
                   </table>
               </div>`
            : `<p class="testing-env__blank">${escapeHtml(this.strings.noPrs)}</p>`;
        const forms = isMaintainer
            ? '<form method="post" id="testing-row-form" class="testing-env__anchor-form"></form>'
            : '';
        return `<div class="testing-env__main">
            <header class="testing-env__bar"><h2 class="testing-env__title">${escapeHtml(this.strings.title)}</h2>${addForm}</header>
            ${forms}${table}
        </div>
        ${this.renderDeploy(payload, isMaintainer)}
        <div class="testing-env__toast" data-toast hidden aria-live="polite"></div>`;
    }

    applyPayload(payload) {
        const focused = focusedSelector(this.root);
        this.root.innerHTML = this.renderPayload(payload);
        if (focused) {
            const successor = this.root.querySelector(focused);
            if (successor) successor.focus();
        }
    }

    async loadStatus(showLoading = false, renderError = true, manageBusy = true) {
        if (manageBusy) this.setBusy(true);
        if (showLoading) this.renderLoading();
        try {
            const payload = await getTestingStatus();
            this.applyPayload(payload);
            return true;
        } catch {
            if (renderError) this.renderError();
            return false;
        } finally {
            if (manageBusy) this.setBusy(false);
        }
    }

    actionResultMessage(action, response) {
        try {
            const url = new URL(response.url, window.location.href);
            if (action.endsWith('/deploy')) {
                if (url.searchParams.has('deploy_failed')) return this.strings.deployFailed;
                if (url.searchParams.has('deploy_unconfigured')) return this.strings.deployUnconfigured;
                if (url.searchParams.has('deploy_triggered')) return this.strings.deployTriggered;
            }
            if (action.endsWith('/refresh')) return this.strings.githubRefreshed;
        } catch {
            // A malformed redirect URL falls back to the generic confirmation.
        }
        return this.strings.actionComplete;
    }

    async runAction(action, fields, message) {
        if (this.busy) return;
        this.setBusy(true);
        this.setToast(message);
        try {
            const response = await postAction(action, fields);
            const loaded = await this.loadStatus(false, false, false);
            this.setToast(loaded ? this.actionResultMessage(action, response) : this.strings.loadError);
        } catch {
            this.setToast(this.strings.actionFailed);
        } finally {
            this.setBusy(false);
        }
    }

    planFor(button) {
        const action = button.getAttribute('formaction');
        const pr = button.dataset.pr;
        if (button.hasAttribute('data-row-toggle')) {
            const verb = action.endsWith('disable') ? this.strings.disabling : this.strings.enabling;
            return { fields: { prs: [pr] }, message: sprintf(verb, pr) };
        }
        if (button.hasAttribute('data-row-action')) {
            const verb = action.endsWith('remove') ? this.strings.removing : this.strings.updating;
            return { fields: { prs: [pr] }, message: sprintf(verb, pr) };
        }
        if (button.hasAttribute('data-deploy')) {
            return { fields: {}, message: this.strings.deploying };
        }
        if (button.hasAttribute('data-refresh')) {
            return { fields: {}, message: `${button.textContent.trim()}…` };
        }
        return null;
    }

    bind() {
        this.root.addEventListener('click', (event) => {
            const button = event.target.closest('button');
            if (!button || !this.root.contains(button)) return;
            if (button.hasAttribute('data-retry')) {
                event.preventDefault();
                this.loadStatus(true);
                return;
            }
            if (!button.hasAttribute('formaction')) return;
            const plan = this.planFor(button);
            if (!plan) return;
            event.preventDefault();
            this.runAction(button.getAttribute('formaction'), plan.fields, plan.message);
        });

        this.root.addEventListener('submit', (event) => {
            if (this.busy) return;
            const form = event.target.closest('form[data-add-form]');
            if (!form || !this.root.contains(form)) return;
            event.preventDefault();
            const input = form.querySelector('input[name="pr"]');
            const value = input?.value.trim();
            if (!value) return;
            this.runAction(form.action, { pr: value }, this.strings.adding);
        });

    }

    /**
     * Re-fetch the panel when the tab regains focus, so state that changed
     * while the user was elsewhere (a deploy finishing, a PR being merged)
     * shows up without an interval timer. The fetch is cheap and the re-render
     * already restores focus, so unlike the old 20s poll this needs no
     * cell-patching machinery. A short dedupe window absorbs browsers that
     * fire both `visibilitychange` and `focus` for the same return to the tab.
     */
    bindFocusRefresh() {
        let lastRefresh = 0;
        const refreshIfVisible = () => {
            if (!this.root.isConnected || this.busy || document.hidden) return;
            const now = Date.now();
            if (now - lastRefresh < 2000) return;
            lastRefresh = now;
            this.loadStatus(false, false);
        };
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') refreshIfVisible();
        });
        window.addEventListener('focus', refreshIfVisible);
    }
}

export function init(root) {
    new TestingStatusPanel(root);
}
