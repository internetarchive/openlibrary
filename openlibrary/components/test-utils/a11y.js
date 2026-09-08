/**
 * Shared setup for Lit component accessibility tests.
 *
 * These tests render the real components and run axe over the resulting
 * shadow DOM, so a change to a component's markup is what makes them fail.
 */
import { axe } from 'jest-axe';

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
    window.matchMedia = jest.fn().mockImplementation((query) => {
        if (!(query in answers)) {
            throw new Error(`stubMatchMedia has no answer for "${query}". Add it to the map in test-utils/a11y.js.`);
        }
        return {
            matches: answers[query],
            media: query,
            onchange: null,
            addEventListener: jest.fn(),
            removeEventListener: jest.fn(),
            addListener: jest.fn(),
            removeListener: jest.fn(),
            dispatchEvent: jest.fn(),
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

export async function checkA11y(node = document.body) {
    return axe(node, AXE_COMPONENT_CONFIG);
}
