/**
 * Shared setup for Lit component accessibility tests.
 *
 * These tests render the real components and run axe-core over the resulting
 * shadow DOM, so a change to a component's markup is what makes them fail.
 */
import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Document-level rules check whole-page structure (landmarks, page headings),
 * which a mounted component fragment can never satisfy.
 */
export const AXE_COMPONENT_CONFIG = {
    rules: {
        region: { enabled: false },
        'landmark-one-main': { enabled: false },
        'page-has-heading-one': { enabled: false },
    },
};

/**
 * Vitest matcher: assert that an axe-core results object has no violations.
 *
 * Usage after `expect.extend({ toHaveNoViolations })`:
 *     const results = await checkA11y();
 *     expect(results).toHaveNoViolations();
 */
export function toHaveNoViolations(received) {
    const pass = received.violations.length === 0;

    const message = () => {
        const headline = this?.isNot
            ? 'expected axe-core to find violations, but none were found'
            : `expected no accessibility violations, but found ${received.violations.length}`;

        const details = received.violations
            .map((v) => {
                const nodes = v.nodes.map((n) => `    - ${n.html}`).join('\n');
                return `  ${v.id}: ${v.description}\n${nodes}`;
            })
            .join('\n');

        return [headline, details].filter(Boolean).join('\n');
    };

    return { message, pass };
}

expect.extend({ toHaveNoViolations });

/**
 * jsdom implements no media queries, so every component that calls
 * matchMedia gets whatever we answer here. Answer only the queries our
 * components actually ask, and throw on anything else, so a new query
 * surfaces as a clear failure rather than a silently wrong `false`.
 *
 * Reduced motion defaults to true: popovers then skip their animation
 * states and reach final markup in a single update.
 */
export function stubMatchMedia({ mobile = false, reducedMotion = true, hover = true } = {}) {
    const answers = {
        '(prefers-reduced-motion: reduce)': reducedMotion,
        '(max-width: 767px)': mobile,
        '(hover: hover) and (pointer: fine)': hover,
    };
    window.matchMedia = vi.fn().mockImplementation((query) => {
        if (!(query in answers)) {
            throw new Error(`stubMatchMedia has no answer for "${query}". Add it to the map in test-utils/a11y.js.`);
        }
        return {
            matches: answers[query],
            media: query,
            onchange: null,
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
            addListener: vi.fn(),
            removeListener: vi.fn(),
            dispatchEvent: vi.fn(),
        };
    });
}

/** Await a Lit element and any Lit children it renders into its shadow root. */
async function settle(el) {
    if (el?.updateComplete) await el.updateComplete;
    for (const child of el?.shadowRoot?.querySelectorAll('*') ?? []) {
        if (child.updateComplete) await child.updateComplete;
    }
}

/** Mount markup, wait for it to render, and return the first element. */
export async function mount(markup) {
    document.body.innerHTML = markup;
    const el = document.body.firstElementChild;
    await settle(el);
    return el;
}

/**
 * jsdom's ElementInternals implements the ARIA properties but none of the
 * form-association methods, which FormAssociatedMixin calls on first render.
 */
export function stubElementInternals() {
    const proto = window.ElementInternals?.prototype;
    if (!proto || proto.setFormValue) return;
    proto.setFormValue = () => {};
    proto.setValidity = () => {};
    proto.checkValidity = () => true;
    proto.reportValidity = () => true;
}

/** Prepare the jsdom environment for rendering a Lit component. */
export function setupComponentEnv(mediaOptions) {
    stubMatchMedia(mediaOptions);
    stubElementInternals();
}

/** Advance past a requestAnimationFrame chain (OlToast defers its announce). */
export function nextFrames(count = 3) {
    return new Promise((resolve) => {
        const step = (n) => (n === 0 ? resolve() : requestAnimationFrame(() => step(n - 1)));
        step(count);
    });
}

/** Open a popover and wait for the panel to render. */
export async function openPopover(el) {
    el.open = true;
    await settle(el);
    return el;
}

export function cleanup() {
    document.body.innerHTML = '';
}

/** Run axe-core over `node` with component-friendly rule overrides. */
export async function checkA11y(node = document.body) {
    return axe.run(node, AXE_COMPONENT_CONFIG);
}
