import {
    FOCUSABLE_SELECTOR,
    findFocusableIndex,
    getDeepActiveElement,
    getTabbableElements,
    getTabbableFromSlot,
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

describe('FOCUSABLE_SELECTOR', () => {
    test('matches the documented controls (button, input, a[href], …)', () => {
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

describe('getTabbableElements', () => {
    // Helper: a host element with an open shadow root whose innerHTML is `html`.
    function hostWithShadow(html) {
        const host = document.createElement('div');
        const root = host.attachShadow({ mode: 'open' });
        root.innerHTML = html;
        document.body.appendChild(host);
        return host;
    }

    test('returns nothing for a null root', () => {
        expect(getTabbableElements(null)).toEqual([]);
    });

    test('collects focusable light-DOM children in document order', () => {
        const root = document.createElement('div');
        root.innerHTML = '<button>a</button><span>x</span><a href="#">b</a><input>';
        document.body.appendChild(root);

        expect(getTabbableElements(root).map(el => el.tagName)).toEqual([
            'BUTTON', 'A', 'INPUT',
        ]);
    });

    test('pierces a nested shadow root — the gap a shallow querySelectorAll misses', () => {
        // A wrapper whose only focusable lives inside a child custom element's
        // shadow root. A shallow querySelectorAll can't see it; the deep walker
        // can.
        const wrapper = document.createElement('div');
        document.body.appendChild(wrapper);
        const host = document.createElement('div');
        wrapper.appendChild(host);
        const root = host.attachShadow({ mode: 'open' });
        root.innerHTML = '<button class="inner">deep</button>';

        // Characterize the shallow util's blind spot…
        expect(wrapper.querySelectorAll(FOCUSABLE_SELECTOR).length).toBe(0);
        // …and prove the deep walker finds it.
        const found = getTabbableElements(wrapper);
        expect(found).toHaveLength(1);
        expect(found[0]).toBe(root.querySelector('.inner'));
    });

    test('treats a focusable host as a single leaf stop and does not descend (today\'s mixin shape)', () => {
        // A custom-element host carrying tabindex (FocusableHostMixin today) is
        // one tab stop; we must not also enumerate its inner button.
        const host = hostWithShadow('<button class="inner">x</button>');
        host.setAttribute('tabindex', '0');

        const found = getTabbableElements(document.body);
        expect(found).toEqual([host]);
        expect(found).not.toContain(host.shadowRoot.querySelector('.inner'));
    });

    test('descends into a delegatesFocus-style host with no host tabindex (target shape)', () => {
        // After the mixin is slimmed to delegatesFocus-only (no host tabindex),
        // the walker should find and return the real inner element directly —
        // so the trap never relies on host.focus() delegation.
        const host = hostWithShadow('<button class="inner">x</button>');

        const found = getTabbableElements(document.body);
        expect(found).toEqual([host.shadowRoot.querySelector('.inner')]);
    });

    test('records both a focusable container and its nested light-DOM focusable', () => {
        // A role="button" row (tabindex="0") with a nested remove button — like
        // the recent-search rows. Native Tab order stops on both, so the walker
        // must record the row AND descend to its button (the shadow-boundary
        // leaf rule only applies to elements that have a shadow root).
        const root = document.createElement('div');
        root.innerHTML =
            '<div class="row" role="button" tabindex="0">' +
            '  <span>label</span><button class="remove">x</button>' +
            '</div>';
        document.body.appendChild(root);

        expect(getTabbableElements(root).map(el => el.className)).toEqual(['row', 'remove']);
    });

    test('exposes exactly one stop for a roving-tabindex composite', () => {
        const host = hostWithShadow(
            '<button tabindex="0" class="active">1</button>' +
            '<button tabindex="-1">2</button>' +
            '<button tabindex="-1">3</button>',
        );

        const found = getTabbableElements(document.body);
        expect(found).toEqual([host.shadowRoot.querySelector('.active')]);
    });

    test('finds a light-DOM trigger inside a wrapper custom element (the ol-select-popover shape)', () => {
        // Wrapper with no shadow root and no host tabindex; its focusable is a
        // light-DOM child (an injected trigger button).
        const wrapper = document.createElement('div');
        wrapper.innerHTML = '<button class="trigger">Language</button>';
        document.body.appendChild(wrapper);

        const found = getTabbableElements(document.body);
        expect(found).toEqual([wrapper.querySelector('.trigger')]);
    });

    test('expands a slot to its assigned light-DOM elements, in slot order', () => {
        // A host that projects its light children through a <slot> in its
        // shadow root — the walker should surface the projected buttons.
        const host = document.createElement('div');
        host.attachShadow({ mode: 'open' }).innerHTML =
            '<button class="before">before</button><slot></slot><button class="after">after</button>';
        host.innerHTML = '<button class="slotted">slotted</button>';
        document.body.appendChild(host);

        expect(getTabbableElements(document.body).map(el => el.className)).toEqual([
            'before', 'slotted', 'after',
        ]);
    });

    test('skips hidden and disabled elements and their subtrees', () => {
        const root = document.createElement('div');
        root.innerHTML =
            '<button class="ok">ok</button>' +
            '<button class="dis" disabled>nope</button>' +
            '<div class="hiddenWrap"><button class="buried">buried</button></div>';
        document.body.appendChild(root);

        // Mark the wrapper as not rendered via the standard API the helper reads.
        root.querySelector('.hiddenWrap').checkVisibility = () => false;
        root.querySelector('.ok').checkVisibility = () => true;
        root.querySelector('.dis').checkVisibility = () => true;

        const found = getTabbableElements(root);
        expect(found.map(el => el.className)).toEqual(['ok']);
    });
});

describe('getTabbableFromSlot', () => {
    test('returns [] when the slot is null', () => {
        expect(getTabbableFromSlot(null)).toEqual([]);
    });

    test('collects direct and descendant focusables from assigned elements, in order', () => {
        const button = document.createElement('button');
        const wrapper = document.createElement('div');
        const inner = document.createElement('input');
        wrapper.appendChild(inner);
        const slot = { assignedElements: () => [button, wrapper] };

        expect(getTabbableFromSlot(slot)).toEqual([button, inner]);
    });

    test('pierces an assigned custom element\'s shadow root', () => {
        // An assigned element whose only focusable lives in its shadow root —
        // a shallow one-slot-deep scan would miss it; the deep walker finds the
        // real inner control.
        const host = document.createElement('div');
        host.attachShadow({ mode: 'open' }).innerHTML = '<button class="deep">x</button>';
        const slot = { assignedElements: () => [host] };

        expect(getTabbableFromSlot(slot)).toEqual([host.shadowRoot.querySelector('.deep')]);
    });

    test('drops hidden/disabled assigned elements', () => {
        const ok = document.createElement('button');
        ok.checkVisibility = () => true;
        const hidden = document.createElement('button');
        hidden.checkVisibility = () => false;
        const slot = { assignedElements: () => [ok, hidden] };

        expect(getTabbableFromSlot(slot)).toEqual([ok]);
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
