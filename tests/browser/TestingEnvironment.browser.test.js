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

test('shows a spinner on the row while its update is in flight', async() => {
    const { pendingPosts } = stubQueuedActions();
    await render(TestingEnvironment, { props: { maintainer: 'true' } });

    await expect.element(page.getByRole('button', { name: 'Update' }).first()).toBeInTheDocument();
    await page.getByRole('button', { name: 'Update' }).first().click();

    // The arrow swaps for a spinner and the button disables until done.
    const updateButton = () => document.querySelector('button[aria-label="Update"]');
    await expect.poll(() => updateButton()?.disabled).toBe(true);
    expect(document.querySelector('.testing-env__row-action .testing-env__spinner')).not.toBeNull();

    pendingPosts.shift().resolve();
    await expect.poll(() => updateButton()?.disabled).toBe(false);
    expect(document.querySelector('.testing-env__row-action .testing-env__spinner')).toBeNull();
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

test('four rapid toggles converge exactly to server state', async() => {
    // Four enables in a row, with a hostile server push landing mid-queue:
    // the push reflects the server after only the first PATCH. It is
    // dropped while the queue drains, and the last queued response confirms
    // everything — the end state must match the server exactly.
    const prs = [13269, 13270, 13271, 13272];
    const staged = { 13269: null, 13270: null, 13271: null, 13272: null };
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
        prs: prs.map(row),
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
            // Mirrors the endpoint: staged flags for every row.
            const echo = prs.map((pr) => ({ pr, pending_active: staged[pr], pending_remove: false }));
            return { ok: true, json: async() => ({ ok: true, prs: echo }) };
        }
        throw new Error(`unexpected fetch: ${url}`);
    };

    // A connected stream that captures its listener so the test can push
    // frames on demand; `streaming` stays true so the fallback poller stays
    // out of the sequence.
    let statusListener;
    class PushableEventSource {
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
        addEventListener(type, listener) {
            if (type === 'status') statusListener = listener;
        }
        close() {
            this.readyState = 2;
        }
    }
    const realEventSource = window.EventSource;
    window.EventSource = PushableEventSource;

    try {
        await render(TestingEnvironment, { props: { maintainer: 'true' } });
        const pressed = (pr) =>
            document.querySelector(`button[aria-label="PR #${pr} on testing"]`)?.getAttribute('aria-pressed');
        const label = (pr) => `PR #${pr} on testing`;

        for (const pr of prs) {
            await expect.poll(() => pressed(pr)).toBe('false');
        }

        for (const pr of prs) {
            await page.getByRole('button', { name: label(pr) }).click();
        }
        // First PATCH on the wire, three queued; all four flipped instantly.
        await expect.poll(() => patchBodies.length).toBe(1);
        for (const pr of prs) {
            await expect.poll(() => pressed(pr)).toBe('true');
        }

        // First request lands; the server now has only row one staged.
        patchResolvers.shift()();
        await expect.poll(() => patchBodies.length).toBe(2);

        // Hostile push: sampled between the server applies, but dropped —
        // pushes pause while the queue drains, and the drain-end response is
        // the confirmation. Nothing may flip.
        statusListener({ data: JSON.stringify(snapshot()) });
        // Nothing may flip back — three requests are still queued.
        for (const pr of prs) {
            await expect.poll(() => pressed(pr)).toBe('true');
        }

        // Drain the rest; every POST staged `active: true` in order.
        // (One at a time: each resolver only exists once the previous
        // request resolves and the queue sends the next.)
        patchResolvers.shift()();
        await expect.poll(() => patchBodies.length).toBe(3);
        patchResolvers.shift()();
        await expect.poll(() => patchBodies.length).toBe(4);
        patchResolvers.shift()();
        expect(patchBodies.map((b) => b.active)).toEqual([true, true, true, true]);

        // Confirming push: the last queued response already applied the same
        // staged flags, so this is a no-op. Then an external change arrives
        // (row four switched off elsewhere): it must render.
        const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
        statusListener({ data: JSON.stringify(snapshot()) });
        await tick();
        staged[13272] = null;
        statusListener({ data: JSON.stringify(snapshot()) });
        await expect.poll(() => pressed(13272)).toBe('false');
        for (const pr of [13269, 13270, 13271]) {
            await expect.poll(() => pressed(pr)).toBe('true');
        }
    } finally {
        window.EventSource = realEventSource;
    }
});

test('a push dropped mid-queue still converges via the last response', async() => {
    // Two toggles; someone else reverts the first mid-queue and its push is
    // dropped (busy). The last queued response was computed from state
    // including the revert, so applying it converges exactly — nothing sticks.
    const prs = [13269, 13270];
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
        prs: prs.map(row),
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
    // Mirrors the endpoint: staged flags for every row, read when the
    // response is built (after any interleaving writes, like the server).
    const echo = () => prs.map((pr) => ({ pr, pending_active: staged[pr], pending_remove: false }));
    window.fetch = async(url, options = {}) => {
        if (url === '/status/testing.json') {
            return { ok: true, json: async() => snapshot() };
        }
        if (url === '/status/testing/prs') {
            const body = JSON.parse(options.body);
            staged[body.prs[0]] = body.active;
            patchBodies.push(body);
            await new Promise((resolve) => patchResolvers.push(resolve));
            return { ok: true, json: async() => ({ ok: true, prs: echo() }) };
        }
        throw new Error(`unexpected fetch: ${url}`);
    };

    let statusListener;
    class PushableEventSource {
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
        addEventListener(type, listener) {
            if (type === 'status') statusListener = listener;
        }
        close() {
            this.readyState = 2;
        }
    }
    const realEventSource = window.EventSource;
    window.EventSource = PushableEventSource;

    try {
        await render(TestingEnvironment, { props: { maintainer: 'true' } });
        const pressed = (pr) =>
            document.querySelector(`button[aria-label="PR #${pr} on testing"]`)?.getAttribute('aria-pressed');

        await expect.poll(() => pressed(13269)).toBe('false');
        await expect.poll(() => pressed(13270)).toBe('false');

        await page.getByRole('button', { name: 'PR #13269 on testing' }).click();
        await page.getByRole('button', { name: 'PR #13270 on testing' }).click();
        await expect.poll(() => patchBodies.length).toBe(1);
        await expect.poll(() => pressed(13269)).toBe('true');
        await expect.poll(() => pressed(13270)).toBe('true');

        // First request lands; the second is queued behind it.
        patchResolvers.shift()();
        await expect.poll(() => patchBodies.length).toBe(2);

        // Someone else reverts the first row; the push is dropped mid-queue,
        // so both rows keep showing their optimistic flips.
        staged[13269] = null;
        statusListener({ data: JSON.stringify(snapshot()) });
        await expect.poll(() => pressed(13269)).toBe('true');
        await expect.poll(() => pressed(13270)).toBe('true');

        // The last response includes the revert: applying it converges.
        patchResolvers.shift()();
        await expect.poll(() => pressed(13269)).toBe('false');
        await expect.poll(() => pressed(13270)).toBe('true');
    } finally {
        window.EventSource = realEventSource;
    }
});
