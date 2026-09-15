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
