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
        { pr: 13269, title: 'First PR', author: 'one', assignee: '', commit: 'abc1234', head_sha: 'def5678', drift: 1, active: true },
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
    expect(new URLSearchParams(calls[0].options.body).getAll('prs')).toEqual(['13269']);

    pendingPosts.shift().resolve();
    await expect.poll(() => calls.length).toBe(2);
    expect(calls[1].url).toBe('/status/pull-latest');
    expect(new URLSearchParams(calls[1].options.body).getAll('prs')).toEqual(['13270', '13271']);

    pendingPosts.shift().resolve();
    await expect.poll(() => calls.length).toBe(3);
    expect(calls[2].url).toBe('/status/deploy');

    pendingPosts.shift().resolve();
});
