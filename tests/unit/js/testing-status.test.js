import { getTestingStatus, testingStatusUrl } from '../../../openlibrary/plugins/openlibrary/js/testing-status/TestingStatusService';
import { init } from '../../../openlibrary/plugins/openlibrary/js/testing-status';

const payload = {
    last_deploy_at: '',
    deploy_started_at: '',
    deploying: false,
    has_pending: false,
    pending_changes: [],
    prs: [{
        pr: 13269,
        title: 'A client-rendered testing panel',
        commit: '1d23364b8c652d6107e2dc685f918551fda5d327',
        active: true,
        added_at: '2026-08-06T15:00:00+00:00',
        added_by: 'openlibrary',
        author: 'author',
        assignee: 'assignee',
        head_sha: '1d23364',
        drift: 0,
        merged: false,
        is_new: false
    }]
};

function flushPromises() {
    return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('Testing Environment JSON panel', () => {
    afterEach(() => {
        jest.restoreAllMocks();
        delete global.fetch;
        document.body.replaceChildren();
    });

    test('uses the FastAPI proxy only on the testing host', () => {
        expect(testingStatusUrl({ hostname: 'localhost' })).toBe('/status/testing.json');
        expect(testingStatusUrl({ hostname: 'testing.openlibrary.org' })).toBe('/_fast/status/testing.json');
        expect(testingStatusUrl({ hostname: 'openlibrary.org' })).toBe('/status/testing.json');
    });

    test('fetches JSON with same-origin credentials', async() => {
        const response = { ok: true, json: jest.fn().mockResolvedValue(payload) };
        global.fetch = jest.fn().mockResolvedValue(response);

        await expect(getTestingStatus()).resolves.toBe(payload);
        expect(global.fetch).toHaveBeenCalledWith('/status/testing.json', {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin'
        });
    });

    test('refreshes JSON after a mutation and shows deploy feedback', async() => {
        const deployPayload = {
            ...payload,
            pending_changes: [{ pr: 13269, title: 'Test PR', kind: 'add', detail: '1d23364' }]
        };
        global.fetch = jest.fn().mockImplementation((url, options) => {
            if (options?.method === 'POST') {
                return Promise.resolve({ ok: true, url: 'http://localhost:8080/status?deploy_triggered=1' });
            }
            return Promise.resolve({ ok: true, json: jest.fn().mockResolvedValue(deployPayload) });
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();
        await flushPromises();
        root.querySelector('[data-deploy]').click();
        await flushPromises();
        await flushPromises();
        await flushPromises();

        expect(global.fetch).toHaveBeenCalledTimes(3);
        expect(root.querySelector('[data-toast]').textContent).toBe('Deploy triggered!');
    });

    test('renders the panel from the JSON response', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(payload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();
        await flushPromises();

        expect(root.querySelector('.testing-env__title').textContent).toContain('Testing Environment');
        expect(root.querySelector('.testing-env__pr-num').textContent).toBe('#13269');
        expect(root.querySelector('.testing-env__pill--ok').textContent).toBe('OK');
        expect(root.querySelectorAll('[data-row-toggle]')).toHaveLength(1);
        // Drift 0 and not merged, so only the delete action shows.
        expect(root.querySelectorAll('[data-row-action]')).toHaveLength(1);
        expect(root.querySelectorAll('[data-bulk]')).toHaveLength(0);
        expect(root.querySelector('input[type="checkbox"]')).toBeNull();
        expect(root.querySelector('[data-deploy]')).not.toBeNull();
        expect(root.querySelector('[data-add-form]')).not.toBeNull();
        expect(root.querySelector('[data-testing-loading]')).toBeNull();

        // Refresh is a deploy-band action now, not a checkbox-gated bulk one.
        const refreshButton = root.querySelector('[data-refresh]');
        expect(refreshButton).not.toBeNull();
        expect(refreshButton.closest('.testing-env__deploy')).not.toBeNull();
        expect(refreshButton.classList.contains('testing-env__btn--small')).toBe(false);
    });

    test('refresh button posts to /status/refresh and shows the sync toast', async() => {
        global.fetch = jest.fn().mockImplementation((url, options) => {
            if (options?.method === 'POST') {
                return Promise.resolve({ ok: true, url: 'http://localhost:8080/status?github_refreshed=1' });
            }
            return Promise.resolve({ ok: true, json: jest.fn().mockResolvedValue(payload) });
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();

        root.querySelector('[data-refresh]').click();
        await flushPromises();
        await flushPromises();
        await flushPromises();

        expect(global.fetch).toHaveBeenCalledWith('/status/refresh', expect.objectContaining({ method: 'POST' }));
        expect(root.querySelector('[data-toast]').textContent).toBe('GitHub status refreshed.');
    });

    test('person cells show an avatar only, with the username on hover', async() => {
        const personPayload = {
            ...payload,
            prs: [{
                ...payload.prs[0],
                author: 'octocat',
                author_avatar: 'https://avatars.githubusercontent.com/u/1?v=4',
                assignee: 'hubot',
                assignee_avatar: ''
            }]
        };
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(personPayload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();
        await flushPromises();

        const personCells = root.querySelectorAll('.testing-env__person');
        expect(personCells).toHaveLength(2);

        // The person column centres its content under the header.
        for (const cell of personCells) {
            expect(cell.closest('td').classList.contains('testing-env__col-person')).toBe(true);
        }

        // Real avatar: picture only, username carried in title/alt, no name text.
        const authorAvatar = personCells[0].querySelector('.testing-env__avatar');
        expect(authorAvatar.tagName).toBe('IMG');
        expect(authorAvatar.title).toBe('octocat');
        expect(authorAvatar.alt).toBe('octocat');
        expect(personCells[0].textContent.trim()).toBe('');

        // Missing avatar URL: letter tile with the username still on hover.
        const assigneeAvatar = personCells[1].querySelector('.testing-env__avatar--fallback');
        expect(assigneeAvatar).not.toBeNull();
        expect(assigneeAvatar.title).toBe('hubot');
        expect(assigneeAvatar.getAttribute('aria-label')).toBe('hubot');
        expect(assigneeAvatar.textContent).toBe('H');
    });

    test('shows update only when a newer commit is available, delete on every row', async() => {
        const actionPayload = {
            ...payload,
            prs: [
                { ...payload.prs[0], pr: 13270, drift: 2 },
                { ...payload.prs[0], pr: 13271, merged: true },
                { ...payload.prs[0], pr: 13272 }
            ]
        };
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(actionPayload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();
        await flushPromises();

        const rowActions = [...root.querySelectorAll('[data-row-action]')];
        expect(rowActions).toHaveLength(4);
        expect(rowActions.map((button) => button.getAttribute('formaction'))).toEqual([
            '/status/pull-latest',
            '/status/remove',
            '/status/remove',
            '/status/remove'
        ]);
        expect(rowActions[0].classList.contains('testing-env__row-action--danger')).toBe(false);
        expect(rowActions[1].classList.contains('testing-env__row-action--danger')).toBe(true);

        // The update arrow sits in the drift cell right after the pill; the
        // actions column holds only the delete buttons.
        const updateButton = root.querySelector('[data-row-action][formaction="/status/pull-latest"]');
        expect(updateButton.closest('.testing-env__drift-cell')).not.toBeNull();
        const stackChildren = [...updateButton.closest('.testing-env__cell-stack').children];
        expect(stackChildren.indexOf(updateButton)).toBeGreaterThan(
            stackChildren.findIndex((child) => child.classList.contains('testing-env__pill'))
        );
        expect(root.querySelectorAll('.testing-env__col-actions [data-row-action]')).toHaveLength(3);
        expect(root.querySelectorAll('.testing-env__col-actions [data-row-action][formaction="/status/pull-latest"]')).toHaveLength(0);
    });

    test('marks a pending change with an hourglass whose hover note names it', async() => {
        const pendingPayload = {
            ...payload,
            prs: [{ ...payload.prs[0], pending_active: true }]
        };
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(pendingPayload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();
        await flushPromises();

        const pending = root.querySelector('.testing-env__pending');
        expect(pending).not.toBeNull();
        expect(pending.textContent).toBe('⏳');
        expect(pending.title).toBe('changes on deploy');
        expect(pending.getAttribute('aria-label')).toBe('changes on deploy');
    });

    test('row delete button removes the PR from the set', async() => {
        global.fetch = jest.fn().mockImplementation((url, options) => {
            if (options?.method === 'POST') {
                return Promise.resolve({ ok: true, url: 'http://localhost:8080/status' });
            }
            return Promise.resolve({ ok: true, json: jest.fn().mockResolvedValue(payload) });
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        root.dataset.maintainer = 'true';
        root.dataset.jenkinsUrl = '';
        document.body.append(root);

        init(root);
        await flushPromises();

        root.querySelector('[data-row-action][formaction="/status/remove"]').click();
        await flushPromises();
        await flushPromises();
        await flushPromises();

        expect(global.fetch).toHaveBeenCalledWith('/status/remove', expect.objectContaining({ method: 'POST' }));
        expect(root.querySelector('[data-toast]').textContent).toBe('Action completed.');
    });

    test('re-fetches status when the tab regains focus', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(payload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        document.body.append(root);

        init(root);
        await flushPromises();

        document.dispatchEvent(new Event('visibilitychange'));
        await flushPromises();
        await flushPromises();

        // One fetch for the initial load, one for the focus refresh.
        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(root.querySelector('[data-testing-loading]')).toBeNull();
    });

    test('dedupes rapid focus and visibility events into one refresh', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(payload)
        });
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        document.body.append(root);

        init(root);
        await flushPromises();

        // Some browsers fire both events when returning to the tab.
        document.dispatchEvent(new Event('visibilitychange'));
        window.dispatchEvent(new Event('focus'));
        document.dispatchEvent(new Event('visibilitychange'));
        await flushPromises();
        await flushPromises();

        expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    test('skips the focus refresh while a load or action is in flight', async() => {
        let resolveInitial;
        global.fetch = jest.fn().mockImplementation(() => new Promise((resolve) => {
            resolveInitial = resolve;
        }));
        const root = document.createElement('section');
        root.dataset.testingEnv = '';
        document.body.append(root);

        init(root);
        await flushPromises();

        // The initial load is still pending, so the panel is busy and the
        // focus refresh must not fire another request.
        document.dispatchEvent(new Event('visibilitychange'));
        await flushPromises();
        expect(global.fetch).toHaveBeenCalledTimes(1);

        resolveInitial({ ok: true, json: jest.fn().mockResolvedValue(payload) });
        await flushPromises();
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });
});
