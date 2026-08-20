import {
    DEFAULT_STRINGS,
    canUpdate,
    decodeAndParseJSON,
    driftPill,
    effectiveActive,
    effectivePendingRemoval,
    faviconEnv,
    formatTime,
    getTestingStatus,
    patchAction,
    postAction,
    sprintf,
    testingStatusUrl,
    timeAgo
} from '../../../openlibrary/components/TestingEnvironment/utils.js';

const pr = {
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
};

describe('Testing Environment utils', () => {
    afterEach(() => {
        jest.restoreAllMocks();
        delete global.fetch;
    });

    test('uses the FastAPI proxy only on the testing host', () => {
        expect(testingStatusUrl({ hostname: 'localhost' })).toBe('/status/testing.json');
        expect(testingStatusUrl({ hostname: 'testing.openlibrary.org' })).toBe('/_fast/status/testing.json');
        expect(testingStatusUrl({ hostname: 'openlibrary.org' })).toBe('/status/testing.json');
    });

    test('fetches JSON with same-origin credentials', async() => {
        const payload = { prs: [pr] };
        const response = { ok: true, json: jest.fn().mockResolvedValue(payload) };
        global.fetch = jest.fn().mockResolvedValue(response);

        await expect(getTestingStatus({ hostname: 'localhost' })).resolves.toBe(payload);
        expect(global.fetch).toHaveBeenCalledWith('/status/testing.json', {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin'
        });
    });

    test('posts actions form-encoded, repeating array fields', async() => {
        const body = { ok: true };
        global.fetch = jest.fn().mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue(body) });

        await expect(postAction('/status/prs', { prs: ['13269', '13270'] })).resolves.toBe(body);

        expect(global.fetch).toHaveBeenCalledWith(
            '/status/prs',
            expect.objectContaining({
                method: 'POST',
                credentials: 'same-origin',
                body: new URLSearchParams([['prs', '13269'], ['prs', '13270']])
            })
        );
    });

    test('patches PR actions as JSON', async() => {
        const body = { ok: true };
        global.fetch = jest.fn().mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue(body) });

        await expect(patchAction('/status/prs/13269', { pending_removal: true })).resolves.toBe(body);

        expect(global.fetch).toHaveBeenCalledWith(
            '/status/prs/13269',
            expect.objectContaining({
                method: 'PATCH',
                credentials: 'same-origin',
                headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ pending_removal: true })
            })
        );
    });

    test('resolves the JSON body of successful posts', async() => {
        // Business failures still resolve: {"ok": false, "error": "<code>"} is
        // a completed request, and the component turns the code into a toast.
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue({ ok: false, error: 'deploy_failed' })
        });

        await expect(postAction('/status/deploy', {})).resolves.toEqual({ ok: false, error: 'deploy_failed' });
    });

    test('rejects failed fetches and posts', async() => {
        global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });

        await expect(getTestingStatus({ hostname: 'localhost' })).rejects.toThrow('500');
        await expect(postAction('/status/prs', {})).rejects.toThrow('failed');
    });

    test('fills %s placeholders in order', () => {
        expect(sprintf('%s change will be applied', 3)).toBe('3 change will be applied');
        expect(sprintf('%s commits behind %s', 4, 'abc1234')).toBe('4 commits behind abc1234');
        expect(sprintf('%s selected', 2)).toBe('2 selected');
    });

    test('detects the favicon environment', () => {
        expect(faviconEnv('/static/images/openlibrary-testing-192x192.png')).toBe('testing');
        expect(faviconEnv('/static/images/openlibrary-development-128x128.png')).toBe('development');
        expect(faviconEnv('/static/images/openlibrary-192x192.png')).toBe('production');
    });

    test('leaves non-openlibrary favicons alone', () => {
        expect(faviconEnv('')).toBeNull();
        expect(faviconEnv('/favicon.ico')).toBeNull();
        expect(faviconEnv('https://example.com/custom.png')).toBeNull();
    });

    test('decodes render_component JSON attributes', () => {
        const encoded = encodeURIComponent(JSON.stringify({ title: 'Testing Environment' }));
        expect(decodeAndParseJSON(encoded)).toEqual({ title: 'Testing Environment' });
    });

    test('formats ISO timestamps for display', () => {
        expect(formatTime('2026-08-06T15:00:00+00:00')).toBe('2026-08-06 15:00');
        expect(formatTime('')).toBe('');
    });

    test('renders relative "X ago" labels and skips invalid input', () => {
        expect(timeAgo(new Date(Date.now() - 5 * 60 * 1000).toISOString())).toMatch(/minute/);
        expect(timeAgo(new Date(Date.now() - 2 * 3600 * 1000).toISOString())).toMatch(/hour/);
        expect(timeAgo('')).toBe('');
        expect(timeAgo('not-a-date')).toBe('');
    });

    test('timeAgo accepts an injectable now so labels tick without new data', () => {
        const started = new Date(Date.now() - 60 * 1000).toISOString();
        expect(timeAgo(started, Date.now())).toMatch(/1 minute/);
        // Two minutes later, same timestamp → the label advances.
        expect(timeAgo(started, Date.now() + 2 * 60 * 1000)).toMatch(/3 minutes/);
    });

    test('resolves the effective toggle state', () => {
        // pending_active is only present when a toggle is staged (server emits
        // it just for that), so its value is the direction to stage.
        expect(effectiveActive({ active: true })).toBe(true);
        expect(effectiveActive({ active: false })).toBe(false);
        expect(effectiveActive({ active: true, pending_active: false })).toBe(false);
        expect(effectiveActive({ active: false, pending_active: true })).toBe(true);
        expect(effectiveActive({ active: true, pending_active: null })).toBe(true);
    });

    test('resolves pending removal state', () => {
        expect(effectivePendingRemoval({ pending_removal: true })).toBe(true);
        expect(effectivePendingRemoval({ pending_removal: false })).toBe(false);
        expect(effectivePendingRemoval({ pending_removal: null })).toBe(false);
        expect(effectivePendingRemoval({})).toBe(false);
        expect(effectivePendingRemoval({ active: true })).toBe(false);
    });

    test('offers pull-latest only when a newer commit is available', () => {
        expect(canUpdate({ ...pr, drift: 2 })).toBe(true);
        expect(canUpdate({ ...pr, drift: 0 })).toBe(false);
        expect(canUpdate({ ...pr, drift: 2, pull_latest_sha: 'abc1234' })).toBe(false);
        expect(canUpdate({ ...pr, drift: -1 })).toBe(false);
    });

    test('decides the drift pill per state', () => {
        const ok = driftPill(pr, DEFAULT_STRINGS);
        expect(ok.label).toBe('OK');
        expect(ok.title).toBe('Up-to-date, pinned at 1d23364');
        expect(ok.href).toBe('');

        const unknown = driftPill({ ...pr, drift: -1 }, DEFAULT_STRINGS);
        expect(unknown.label).toBe('?');
        expect(unknown.href).toContain('/commit/1d23364');

        const behind = driftPill({ ...pr, drift: 3 }, DEFAULT_STRINGS);
        expect(behind.label).toBe('-3');
        expect(behind.title).toBe('3 commits behind 1d23364');
        expect(behind.href).toContain('/compare/1d23364b8c652d6107e2dc685f918551fda5d327...1d23364');

        const behindWithoutSha = driftPill({ ...pr, drift: 1, head_sha: '' }, DEFAULT_STRINGS);
        expect(behindWithoutSha.href).toBe('');
        expect(behindWithoutSha.title).toBe('1 commit behind 1d23364');
    });
});
