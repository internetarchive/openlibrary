/**
 * Browser-mode coverage for the Vue/Lit boundary in TestingEnvironment.
 *
 * The toast is created imperatively by Vue but rendered and dismissed by Lit.
 * Importing the Lit entry point here mirrors the page's shared component bundle
 * without mocking the custom elements.
 */
import { expect, test } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-vue';
import TestingEnvironment from '../../openlibrary/components/TestingEnvironment.vue';
import '../../openlibrary/components/lit/OlIcon.js';
import '../../openlibrary/components/lit/OlToastRegion.js';

const payload = {
    prs: [],
    pending_changes: [{ kind: 'add', pr: 13269, title: 'A client-rendered testing panel' }],
    deploying: false,
    deploy_result: ''
};

const updatePayload = {
    ...payload,
    prs: [
        { pr: 13269, title: 'First PR', author: 'one', assignee: '', commit: 'abc1234', head_sha: 'def5678', drift: 1, active: true, draft: true },
        { pr: 13270, title: 'Second PR', author: 'two', assignee: '', commit: 'abc1234', head_sha: 'def5678', drift: 1, active: true },
        { pr: 13271, title: 'Third PR', author: 'three', assignee: '', commit: 'abc1234', head_sha: 'def5678', drift: 1, active: true }
    ]
};

function stubStatusAndFailedDeploy() {
    const calls = [];
    window.fetch = async(url, options = {}) => {
        calls.push({ url, options });
        if (options.method === 'POST') {
            return {
                ok: true,
                json: async() => ({ ok: false, error: 'deploy_failed' })
            };
        }
        return { ok: true, json: async() => payload };
    };
    return calls;
}

function stubQueuedActions() {
    const calls = [];
    const pendingPosts = [];
    window.fetch = async(url, options = {}) => {
        if (options.method === 'POST') {
            const request = { url, options };
            calls.push(request);
            await new Promise((resolve) => pendingPosts.push({ request, resolve }));
            return { ok: true, json: async() => ({ ok: true }) };
        }
        return { ok: true, json: async() => updatePayload };
    };
    return { calls, pendingPosts };
}

test('renders an action failure through the shared Lit toast region', async() => {
    const calls = stubStatusAndFailedDeploy();

    await render(TestingEnvironment, {
        props: { maintainer: 'true' }
    });

    await expect.element(page.getByRole('button', { name: 'Deploy' })).toBeInTheDocument();
    await page.getByRole('button', { name: 'Deploy' }).click();

    const region = document.querySelector('ol-toast-region');
    expect(region).not.toBeNull();
    const toast = region.querySelector('ol-toast');
    expect(toast).not.toBeNull();

    await expect.poll(() => toast.shadowRoot.querySelector('[role="alert"]')?.textContent)
        .toContain('Jenkins did not accept the build');
    expect(toast.getAttribute('type')).toBe('error');
    expect(toast.getAttribute('timeout')).toBe('6000');
    expect(calls.filter(({ options }) => options.method === 'POST')).toHaveLength(1);
});

test('the Lit toast is removed after the Vue owner unmounts', async() => {
    stubStatusAndFailedDeploy();
    const app = await render(TestingEnvironment, {
        props: { maintainer: 'true' }
    });

    await expect.element(page.getByRole('button', { name: 'Deploy' })).toBeInTheDocument();
    await page.getByRole('button', { name: 'Deploy' }).click();
    await expect.poll(() => document.querySelector('ol-toast')).not.toBeNull();

    app.unmount();
    await expect.poll(() => document.querySelector('ol-toast')).toBeNull();
});

test('marks draft pull requests in the testing table', async() => {
    window.fetch = async() => ({ ok: true, json: async() => updatePayload });

    await render(TestingEnvironment, { props: { maintainer: 'true' } });

    // The draft mark is an icon named "Draft", not a "[Draft]" text prefix.
    await expect.element(page.getByRole('img', { name: 'Draft' })).toBeInTheDocument();
    await expect.element(page.getByRole('link', { name: 'First PR' })).toBeInTheDocument();
});

test('queues and batches rapid updates before deploying', async() => {
    const { calls, pendingPosts } = stubQueuedActions();
    await render(TestingEnvironment, { props: { maintainer: 'true' } });

    await expect.element(page.getByRole('button', { name: 'Update' }).first()).toBeInTheDocument();
    const updates = page.getByRole('button', { name: 'Update' });
    await updates.nth(0).click();
    await updates.nth(1).click();
    await updates.nth(2).click();
    await page.getByRole('button', { name: 'Deploy' }).click();

    await expect.poll(() => calls.length).toBe(1);
    expect(calls[0].url).toBe('/status/pull-latest');
    expect(JSON.parse(calls[0].options.body)).toEqual({ prs: [13269] });

    pendingPosts.shift().resolve();
    await expect.poll(() => calls.length).toBe(2);
    expect(calls[1].url).toBe('/status/pull-latest');
    expect(JSON.parse(calls[1].options.body)).toEqual({ prs: [13270, 13271] });

    pendingPosts.shift().resolve();
    await expect.poll(() => calls.length).toBe(3);
    expect(calls[2].url).toBe('/status/deploy');

    pendingPosts.shift().resolve();
});

test('applies status pushed over the event stream', async() => {
    const fetchUrls = [];
    window.fetch = async(url) => {
        fetchUrls.push(url);
        // Only ever serves the pre-stream payload: updatePayload can only
        // arrive through the stream, so the assertion below proves it did.
        return { ok: true, json: async() => payload };
    };

    let statusListener;
    class FakeEventSource {
        constructor(url) {
            this.url = url;
            this.readyState = 0;
        }
        addEventListener(type, listener) {
            if (type === 'status') statusListener = listener;
        }
        close() {
            this.readyState = 2;
        }
    }
    const realEventSource = window.EventSource;
    window.EventSource = FakeEventSource;

    try {
        await render(TestingEnvironment, { props: { maintainer: 'true' } });
        await expect.element(page.getByText('A client-rendered testing panel')).toBeInTheDocument();

        statusListener({ data: JSON.stringify(updatePayload) });
        await expect.element(page.getByRole('img', { name: 'Draft' })).toBeInTheDocument();

        expect(fetchUrls.length).toBeGreaterThan(0);
        expect(fetchUrls.every((url) => url === '/status/testing.json')).toBe(true);
    } finally {
        window.EventSource = realEventSource;
    }
});

test('rapid toggles keep the second row on (no flicker)', async() => {
    // Server-side staged state: applied synchronously when each PATCH lands,
    // served back on every GET — so a GET between two queued PATCHes
    // predates the second one.
    const staged = { 13269: null, 13270: null };
    const patchBodies = [];
    const patchResolvers = [];
    const row = (pr) => ({
        pr,
        title: `PR ${pr}`,
        author: 'one',
        assignee: '',
        commit: 'abc1234',
        head_sha: 'def5678',
        drift: 0,
        active: false,
        pending_active: staged[pr],
        in_set: true
    });
    const snapshot = () => ({
        prs: [row(13269), row(13270)],
        pending_changes: [],
        deploying: false,
        deploy_result: '',
        deploy_started_at: '',
        deploy_finished_at: '',
        deploy_stage: '',
        last_deploy_at: '',
        deployed_by: '',
        has_pending: false
    });
    window.fetch = async(url, options = {}) => {
        if (url === '/status/testing.json') {
            return { ok: true, json: async() => snapshot() };
        }
        if (url === '/status/testing/prs') {
            const body = JSON.parse(options.body);
            staged[body.prs[0]] = body.active;
            patchBodies.push(body);
            await new Promise((resolve) => patchResolvers.push(resolve));
            return { ok: true, json: async() => ({ ok: true }) };
        }
        throw new Error(`unexpected fetch: ${url}`);
    };

    // A connected-but-silent stream: no pushes, and `streaming` stays true
    // so the fallback poller can't slip extra GETs into the sequence.
    class QuietEventSource {
        constructor() {
            this.readyState = 1;
            this._open = null;
        }
        set onopen(fn) {
            this._open = fn;
            setTimeout(() => this._open?.(), 0);
        }
        get onopen() {
            return this._open;
        }
        set onerror(fn) {
            this._error = fn;
        }
        get onerror() {
            return this._error;
        }
        addEventListener() {}
        close() {
            this.readyState = 2;
        }
    }
    const realEventSource = window.EventSource;
    window.EventSource = QuietEventSource;

    try {
        await render(TestingEnvironment, { props: { maintainer: 'true' } });
        const pressed = (pr) =>
            document.querySelector(`button[aria-label="PR #${pr} on testing"]`)?.getAttribute('aria-pressed');

        // Gate on the fresh snapshot: a cached payload from an earlier test
        // may render first, then the mount re-fetch replaces it.
        await expect.poll(() => pressed(13269)).toBe('false');
        await expect.poll(() => pressed(13270)).toBe('false');

        await page.getByRole('button', { name: 'PR #13269 on testing' }).click();
        await page.getByRole('button', { name: 'PR #13270 on testing' }).click();
        // The first PATCH is on the wire; the second is queued behind it.
        await expect.poll(() => patchBodies.length).toBe(1);

        // Both flip instantly (optimistic).
        await expect.poll(() => pressed(13269)).toBe('true');
        await expect.poll(() => pressed(13270)).toBe('true');

        // Let the first request finish. The intermediate re-fetch predates
        // the queued second PATCH — it must not clobber its optimistic flip.
        patchResolvers.shift()();
        // Once the second PATCH is on the wire, any intermediate re-fetch
        // has fully applied.
        await expect.poll(() => patchBodies.length).toBe(2);
        await expect.poll(() => pressed(13270)).toBe('true');

        patchResolvers.shift()();
        await expect.poll(() => pressed(13269)).toBe('true');
        await expect.poll(() => pressed(13270)).toBe('true');
    } finally {
        window.EventSource = realEventSource;
    }
});
