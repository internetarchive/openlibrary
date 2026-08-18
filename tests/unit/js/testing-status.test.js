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
        expect(root.querySelectorAll('[data-bulk]')).toHaveLength(5);
        expect(root.querySelector('[data-select-all]')).not.toBeNull();
        expect(root.querySelector('[data-deploy]')).not.toBeNull();
        expect(root.querySelector('[data-add-form]')).not.toBeNull();
        expect(root.querySelector('[data-testing-loading]')).toBeNull();
    });

    test('keeps update and remove row actions for qualifying PRs', async() => {
        const actionPayload = {
            ...payload,
            prs: [
                { ...payload.prs[0], pr: 13270, drift: 2 },
                { ...payload.prs[0], pr: 13271, merged: true }
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
        expect(rowActions).toHaveLength(2);
        expect(rowActions.map((button) => button.getAttribute('formaction'))).toEqual([
            '/status/pull-latest',
            '/status/remove'
        ]);
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
