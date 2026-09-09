/**
 * Unit tests for <ol-icon>. The point of the element is that one usage works
 * everywhere client-side, so the cases that matter are: it draws without the
 * sprite, it draws the same nested in another component's shadow root, and a
 * bad name complains instead of rendering an invisible nothing.
 */
import { LitElement, html } from 'lit';

import { OlIcon } from '../../../openlibrary/components/lit/OlIcon.js';

/** A stand-in for any component that wants an icon in its own shadow DOM. */
class IconHost extends LitElement {
    render() {
        return html`<ol-icon name="chevron-left" size="lg"></ol-icon>`;
    }
}
customElements.define('icon-host', IconHost);

/** Append markup, then wait for every element in it to finish its first render. */
async function mount(markup) {
    document.body.innerHTML = markup;
    const host = document.body.firstElementChild;
    await host.updateComplete;
    return host;
}

afterEach(() => {
    document.body.innerHTML = '';
    jest.restoreAllMocks();
});

describe('rendering', () => {
    test('inlines the glyph into its own shadow root', async() => {
        const icon = await mount('<ol-icon name="search"></ol-icon>');
        const svg = icon.shadowRoot.querySelector('svg');

        expect(svg).not.toBeNull();
        expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
        expect(svg.getAttribute('stroke')).toBe('currentColor');
        // Inlined, not referenced — the sprite is unreachable from a shadow root.
        expect(svg.querySelector('use')).toBeNull();
        expect(svg.querySelector('circle')).not.toBeNull();
    });

    test('draws different glyphs for different names', async() => {
        const search = await mount('<ol-icon name="search"></ol-icon>');
        const searchMarkup = search.shadowRoot.innerHTML;

        const globe = await mount('<ol-icon name="globe"></ol-icon>');
        expect(globe.shadowRoot.innerHTML).not.toBe(searchMarkup);
    });

    test('redraws when the name changes', async() => {
        const icon = await mount('<ol-icon name="search"></ol-icon>');
        const before = icon.shadowRoot.innerHTML;

        icon.name = 'globe';
        await icon.updateComplete;
        expect(icon.shadowRoot.innerHTML).not.toBe(before);
    });

    test('renders nothing without a name', async() => {
        const icon = await mount('<ol-icon></ol-icon>');
        expect(icon.shadowRoot.querySelector('svg')).toBeNull();
    });

    test('warns and renders nothing for an unknown name', async() => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

        const icon = await mount('<ol-icon name="not-an-icon"></ol-icon>');

        expect(icon.shadowRoot.querySelector('svg')).toBeNull();
        expect(warn).toHaveBeenCalledWith(expect.stringContaining('not-an-icon'));
    });
});

describe('inside another shadow root', () => {
    test('draws the same glyph it would in the light DOM', async() => {
        const host = await mount('<icon-host></icon-host>');
        const icon = host.shadowRoot.querySelector('ol-icon');
        await icon.updateComplete;

        expect(icon).toBeInstanceOf(OlIcon);
        expect(icon.shadowRoot.querySelector('svg path')).not.toBeNull();

        const standalone = await mount('<ol-icon name="chevron-left" size="lg"></ol-icon>');
        expect(icon.shadowRoot.innerHTML).toBe(standalone.shadowRoot.innerHTML);
    });
});

describe('accessibility', () => {
    test('is hidden from assistive tech without a label', async() => {
        const icon = await mount('<ol-icon name="search"></ol-icon>');

        expect(icon.getAttribute('aria-hidden')).toBe('true');
        expect(icon.hasAttribute('role')).toBe(false);
    });

    test('a label names the host as an image', async() => {
        const icon = await mount('<ol-icon name="globe" label="Language"></ol-icon>');

        expect(icon.getAttribute('role')).toBe('img');
        expect(icon.getAttribute('aria-label')).toBe('Language');
        expect(icon.hasAttribute('aria-hidden')).toBe(false);
    });

    test('clearing the label hides it again', async() => {
        const icon = await mount('<ol-icon name="globe" label="Language"></ol-icon>');

        icon.label = '';
        await icon.updateComplete;
        expect(icon.getAttribute('aria-hidden')).toBe('true');
        expect(icon.hasAttribute('aria-label')).toBe(false);
    });
});
