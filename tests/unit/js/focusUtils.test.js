import {
    FOCUSABLE_SELECTOR,
    findFocusableIndex,
    getDeepActiveElement,
    getFocusableFromSlot,
    isFocusable,
} from '../../../openlibrary/components/lit/utils/focus-utils.js';

// jsdom (used by jest-environment-jsdom 26) implements neither layout nor
// `Element.checkVisibility`. We mock checkVisibility on individual elements
// in the visibility tests below — the runtime helper prefers it when present.

function makeButton(label, { disabled = false, hidden = false } = {}) {
    const btn = document.createElement('button');
    btn.textContent = label;
    if (disabled) btn.disabled = true;
    // Simulate display:none / visibility:hidden via the standard API.
    btn.checkVisibility = () => !hidden;
    return btn;
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('isFocusable', () => {
    test('returns true for a plain enabled element with no visibility hook', () => {
        const btn = document.createElement('button');
        expect(isFocusable(btn)).toBe(true);
    });

    test('returns false for disabled elements', () => {
        const btn = makeButton('go', { disabled: true });
        expect(isFocusable(btn)).toBe(false);
    });

    test('returns false when checkVisibility reports the element is not rendered', () => {
        const btn = makeButton('go', { hidden: true });
        expect(isFocusable(btn)).toBe(false);
    });

    test('returns true when checkVisibility reports the element is rendered', () => {
        const btn = makeButton('go');
        expect(isFocusable(btn)).toBe(true);
    });
});

describe('getFocusableFromSlot', () => {
    test('returns [] when the slot is null', () => {
        expect(getFocusableFromSlot(null)).toEqual([]);
    });

    test('includes directly focusable assigned elements and their focusable descendants', () => {
        const button = makeButton('one');
        const wrapper = document.createElement('div');
        const inner  = makeButton('two');
        wrapper.appendChild(inner);

        const slot = {
            assignedElements: () => [button, wrapper],
        };

        expect(getFocusableFromSlot(slot)).toEqual([button, inner]);
    });

    test('omits assigned elements that are disabled or hidden — the bug', () => {
        // This is the regression that produced the "stuck on Escape / Clear
        // all" report: the focus trap kept hidden buttons in its tab list and
        // `.focus()` on them was a silent no-op.
        const visible = makeButton('visible');
        const hidden  = makeButton('hidden',   { hidden: true });
        const disabled = makeButton('disabled', { disabled: true });

        const slot = { assignedElements: () => [visible, hidden, disabled] };

        expect(getFocusableFromSlot(slot)).toEqual([visible]);
    });

    test('also drops hidden focusable descendants of a wrapper', () => {
        const wrapper = document.createElement('div');
        const visible = makeButton('visible');
        const hidden  = makeButton('hidden', { hidden: true });
        wrapper.append(visible, hidden);

        const slot = { assignedElements: () => [wrapper] };

        expect(getFocusableFromSlot(slot)).toEqual([visible]);
    });

    test('matches the documented FOCUSABLE_SELECTOR (button, input, a[href], …)', () => {
        // A meta-test: a regression in the selector string would silently break
        // every focus trap built on top of this util.
        expect(FOCUSABLE_SELECTOR).toMatch(/button/);
        expect(FOCUSABLE_SELECTOR).toMatch(/input/);
        expect(FOCUSABLE_SELECTOR).toMatch(/\[href\]/);
        expect(FOCUSABLE_SELECTOR).toMatch(/tabindex/);
    });
});

describe('getDeepActiveElement', () => {
    test('returns document.activeElement when there are no shadow roots in the focus chain', () => {
        const btn = document.createElement('button');
        document.body.appendChild(btn);
        btn.focus();
        expect(getDeepActiveElement()).toBe(btn);
    });

    test('descends into shadow roots to find the actually focused element', () => {
        const host = document.createElement('div');
        document.body.appendChild(host);
        const root = host.attachShadow({ mode: 'open' });
        const inner = document.createElement('button');
        root.appendChild(inner);
        inner.focus();

        // document.activeElement points to the shadow host; the deep helper
        // must drill through to the inner button.
        expect(getDeepActiveElement()).toBe(inner);
    });
});

describe('findFocusableIndex', () => {
    test('returns the index when activeElement is itself in the list', () => {
        const a = document.createElement('button');
        const b = document.createElement('button');
        expect(findFocusableIndex([a, b], b)).toBe(1);
    });

    test('returns -1 when activeElement is unrelated to the focusable list', () => {
        const a = document.createElement('button');
        const orphan = document.createElement('button');
        expect(findFocusableIndex([a], orphan)).toBe(-1);
    });

    test('climbs the parent chain to find an ancestor that is in the list', () => {
        // Mirrors a wrapper-with-deep-focus pattern (e.g. light-DOM trigger
        // inside a div that's tracked in the trap).
        const wrapper = document.createElement('div');
        const inner = document.createElement('button');
        wrapper.appendChild(inner);
        document.body.appendChild(wrapper);

        expect(findFocusableIndex([wrapper], inner)).toBe(0);
    });

    test('crosses a shadow boundary to find the host in the list', () => {
        // This is the case that matters for ol-options-popover / ol-select-popover:
        // the trap tracks the custom-element host, but the actually focused
        // element is a button inside its shadow root.
        const host = document.createElement('div');
        document.body.appendChild(host);
        const root = host.attachShadow({ mode: 'open' });
        const inner = document.createElement('button');
        root.appendChild(inner);

        expect(findFocusableIndex([host], inner)).toBe(0);
    });
});
