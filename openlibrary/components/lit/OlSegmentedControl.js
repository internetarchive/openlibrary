import { LitElement, html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';

/**
 * OlSegmentedControl - A single-select control styled like ol-button.
 *
 * Renders a row of mutually-exclusive options (a radio group): exactly one is
 * selected at a time. It shares ol-button's height tokens and visual language,
 * so a same-size segmented control and button line up at the same height.
 *
 * Options are declared as light-DOM <ol-segment> children carrying a `value`
 * attribute; their content is the label — plain text, or markup such as an
 * <svg> icon. Icon-only segments must add a `label` attribute to name the radio
 * (used as the aria-label and a hover title). Children are read once on connect
 * and re-rendered as accessible radios in the shadow root, so the control needs
 * no per-option wiring from the consuming page.
 *
 * Contains no application logic — the consuming page owns what a selection
 * *does*. Listen for the change event (or read `.value`).
 *
 * @element ol-segmented-control
 *
 * @prop {String}  value           - The selected option's value. Reflected; defaults to the first enabled option.
 * @prop {String}  size            - "small" | "medium" | "large". Default: "medium"
 * @prop {Boolean} disabled        - Disables the whole control.
 * @prop {Boolean} fullWidth       - Stretch to fill the container; options share the width equally.
 * @prop {String}  accessibleLabel - aria-label for the radio group. Default: none.
 *
 * @fires ol-segmented-control-change - Fired on user selection. detail: { value: String }
 *
 * @slot - One or more <ol-segment value="…">Label</ol-segment> option elements.
 *   A segment's content may be text or markup (e.g. an icon); add a `label`
 *   attribute on icon-only segments for the accessible name.
 *
 * @example
 *   <ol-segmented-control value="list" accessible-label="View">
 *     <ol-segment value="grid">Grid</ol-segment>
 *     <ol-segment value="list">List</ol-segment>
 *   </ol-segmented-control>
 *
 * @example
 *   <ol-segmented-control value="grid" accessible-label="View">
 *     <ol-segment value="grid" label="Grid"><svg ...></svg></ol-segment>
 *     <ol-segment value="list" label="List"><svg ...></svg></ol-segment>
 *   </ol-segmented-control>
 */
export class OlSegmentedControl extends LitElement {
    static properties = {
        value: { type: String, reflect: true },
        size: { type: String, reflect: true },
        disabled: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
        _options: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            vertical-align: middle;

            --pill-radius: var(--border-radius-button);

            /* A crisp ease-out (no overshoot) for the slide — the pill should
               feel like it snaps to the new segment, not bounce. */
            --slide-duration: 0.25s;
            --slide-ease: cubic-bezier(0.32, 0.72, 0, 1);
        }

        :host([full-width]) {
            display: flex;
            width: 100%;
        }

        :host([disabled]) {
            opacity: 0.55;
            cursor: not-allowed;
        }

        /* A light-grey inset track. The selected segment floats inside it as a
           white pill, so the track padding sets the gap around that pill.

           Two stacked layers ride inside the track, both built from the same
           option list so they line up pixel-for-pixel:
             • .layer--base   — the real radio buttons, painted in the dimmed
               (inactive) colour. They own all interaction and a11y.
             • .layer--active — an aria-hidden duplicate painted in the active
               (dark) colour, clipped to just the selected segment.
           Sliding the clip-path of the active layer makes a segment's colour
           flip exactly where the pill's edge crosses it, so the colour change
           travels *with* the pill instead of toggling instantly. The white pill
           itself is a separate .pill element (clip-path would eat its shadow). */
        .track {
            position: relative;
            isolation: isolate;
            display: inline-flex;
            box-sizing: border-box;
            height: var(--control-height-medium);
            padding: var(--spacing-3xs);
            border-radius: var(--border-radius-button);
            background-color: var(--lightest-grey);
        }

        :host([full-width]) .track {
            display: flex;
            width: 100%;
        }

        .layer {
            display: inline-flex;
        }

        /* The interactive layer sits above the pill so its text reads on top of
           the white fill; the active (clipped) layer sits above both. It's a
           flex item of the track, so align-items: stretch already sizes it to
           the track's content height — its segments fill that via height: 100%. */
        .layer--base {
            position: relative;
            z-index: 1;
            height: 100%;
        }

        :host([full-width]) .layer--base {
            flex: 1;
        }

        .layer--active {
            position: absolute;
            z-index: 2;
            inset: var(--spacing-3xs);
            display: flex;
            pointer-events: none;
            /* clip-path (revealing only the selected segment's slice of the
               dark-text layer) is set directly by _measure() so its changes
               trigger the transition — an inherited var() change would not. */
            visibility: hidden;
        }

        /* The selected segment's text. Doubled class (.segment.segment--ghost)
           so this beats the later, equal-specificity ".segment" color rule —
           otherwise the cascade resolves the ghost to --accessible-grey and the
           selected segment looks dimmed instead of full-strength #333. */
        .segment.segment--ghost {
            color: var(--dark-grey);
        }

        /* The sliding white pill — carries the raised look the selected segment
           used to draw itself. translateX + width walk it to the active
           segment; its shadow can't be clipped, hence its own element. */
        .pill {
            position: absolute;
            z-index: 0;
            top: var(--spacing-3xs);
            bottom: var(--spacing-3xs);
            left: var(--spacing-3xs);
            /* width + translateX are set directly by _measure() (see above). */
            width: 0;
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--pill-radius);
            background-color: var(--white);
            box-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0 color-mix(in srgb, var(--white) 35%, var(--control-surface));
            visibility: hidden;
        }

        /* Both are hidden until _measure() has placed them (avoids a flash of
           an unpositioned pill on first paint). */
        .track.is-ready .pill,
        .track.is-ready .layer--active {
            visibility: visible;
        }

        /* Transitions are enabled one frame after the initial placement so the
           pill appears in position instead of sliding in from the left. */
        .track.is-animated .pill {
            transition:
                transform var(--slide-duration) var(--slide-ease),
                width var(--slide-duration) var(--slide-ease);
        }

        .track.is-animated .layer--active {
            transition: clip-path var(--slide-duration) var(--slide-ease);
        }

        .segment {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            height: 100%;
            padding: 0 var(--spacing-md);
            /* Transparent border on every segment keeps widths stable, so
               selecting one doesn't shift its neighbors when its border shows. */
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            background-color: transparent;
            /* Non-selected segments are dimmed so the selected one reads as
               active; hover and the selected pill darken back to full strength. */
            color: var(--accessible-grey);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-control);
            white-space: nowrap;
            cursor: pointer;
            user-select: none;
            /* Only the selected pill crossfades in (background/border/shadow).
               Color is intentionally NOT transitioned so hover darkening is
               instant — the hover effect must give immediate feedback. */
            transition:
                background-color 0.15s,
                border-color 0.15s,
                box-shadow 0.15s;
        }

        :host([full-width]) .segment {
            flex: 1 1 0;
        }

        /* Icon segments: size the glyph to the control and let it inherit the
           segment's color so it tracks selected/hover states like text does. */
        .segment svg {
            display: block;
            width: 18px;
            height: 18px;
        }

        @media (hover: hover) and (pointer: fine) {
            .segment:not([aria-checked="true"]):not(:disabled):hover {
                color: var(--dark-grey);
            }
        }

        .segment:active:not(:disabled) {
            transform: scale(0.97);
        }

        /* The selected segment's raised-white-pill look now lives on the
           floating .pill, and its dark text on the clipped .layer--active — so
           the interactive base button stays dimmed and transparent even when
           selected (its text reads through from the active layer above). */

        .segment:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }

        .segment:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* Sizes — mirror ol-button so same-size controls line up. */
        :host([size="small"]) .track {
            height: var(--control-height-small);
        }

        :host([size="small"]) .segment {
            padding: 0 var(--spacing-sm);
            font-size: var(--font-size-label-medium);
        }

        :host([size="small"]) .segment svg {
            width: 16px;
            height: 16px;
        }

        :host([size="large"]) .track {
            height: var(--control-height-large);
        }

        :host([size="large"]) .segment {
            padding: 0 var(--spacing-lg);
            font-size: var(--font-size-body-large);
        }

        :host([size="large"]) .segment svg {
            width: 20px;
            height: 20px;
        }

        @media (prefers-reduced-motion: reduce) {
            .segment {
                transition: none;
            }

            .segment:active:not(:disabled) {
                transform: none;
            }

            /* The pill and active layer still jump straight to the selected
               segment (positioned by JS) — just without the slide. */
            .track.is-animated .pill,
            .track.is-animated .layer--active {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.value = null;
        this.size = 'medium';
        this.disabled = false;
        this.fullWidth = false;
        this.accessibleLabel = null;
        this._options = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._harvestOptions();
    }

    // Read the declarative <ol-segment> children into a plain options array.
    // The light-DOM children stay in the DOM (hidden via ol-components.css) but
    // are never slotted — the shadow root renders the interactive radios.
    _harvestOptions() {
        this._options = Array.from(this.querySelectorAll('ol-segment')).map((el) => {
            const text = el.textContent.trim();
            // A segment with element children carries markup (e.g. an icon);
            // render that verbatim. A text-only segment renders its plain text.
            const isMarkup = el.children.length > 0;
            return {
                value: el.getAttribute('value') ?? text,
                content: isMarkup ? el.innerHTML.trim() : text,
                isMarkup,
                // Accessible name: the `label` attribute, else the text. Icon-only
                // segments have no text, so they rely on `label`.
                accessibleLabel: el.getAttribute('label') ?? text,
                disabled: el.hasAttribute('disabled'),
            };
        });

        // A segmented control always has a selection. If value is unset or
        // doesn't match an option, fall back to the first enabled option.
        const hasValid = this._options.some((o) => o.value === this.value && !o.disabled);
        if (!hasValid) {
            const firstEnabled = this._options.find((o) => !o.disabled);
            this.value = firstEnabled ? firstEnabled.value : null;
        }
    }

    firstUpdated() {
        this._track = this.renderRoot.querySelector('.track');
        // Place the pill/active layer, reveal them, then enable transitions one
        // frame later so the first placement doesn't animate from the origin.
        this._measure();
        this._track.classList.add('is-ready');
        requestAnimationFrame(() => this._track?.classList.add('is-animated'));
        // Re-measure on any reflow: size/full-width changes, late web-font
        // metrics, or the container resizing around a full-width control.
        this._resizeObserver = new ResizeObserver(() => this._measure());
        this._resizeObserver.observe(this._track);
    }

    updated(changed) {
        // Selection moved — walk the pill and clip to the new segment.
        if (changed.has('value')) this._measure();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
    }

    // Move the pill (translateX + width) and the active layer's clip window onto
    // the selected segment. The geometry is set directly on each element (not via
    // an inherited custom property) so the changes actually trigger their CSS
    // transitions. Measured relative to the base layer, so the values are
    // independent of the track's padding and of where the control sits on the page.
    _measure() {
        const track = this._track;
        if (!track) return;
        const base = track.querySelector('.layer--base');
        const activeBtn = track.querySelector('.segment[aria-checked="true"]');
        const pill = track.querySelector('.pill');
        const activeLayer = track.querySelector('.layer--active');
        if (!base || !activeBtn || !pill || !activeLayer) return;

        const baseRect = base.getBoundingClientRect();
        const btnRect = activeBtn.getBoundingClientRect();
        const x = btnRect.left - baseRect.left;
        const w = btnRect.width;
        const right = baseRect.width - x - w;

        pill.style.transform = `translateX(${x}px)`;
        pill.style.width = `${w}px`;
        activeLayer.style.clipPath = `inset(0 ${right}px 0 ${x}px round var(--pill-radius))`;
    }

    // Index of the option that owns the roving tabindex / arrow-key focus.
    get _activeIndex() {
        const i = this._options.findIndex((o) => o.value === this.value);
        if (i !== -1) return i;
        return this._options.findIndex((o) => !o.disabled);
    }

    _select(value, { focus = false } = {}) {
        if (value === this.value) return;
        this.value = value;
        this.dispatchEvent(new CustomEvent('ol-segmented-control-change', {
            bubbles: true,
            composed: true,
            detail: { value },
        }));
        if (focus) {
            this.updateComplete.then(() => {
                const btn = this.renderRoot.querySelector('.segment[aria-checked="true"]');
                if (btn) btn.focus();
            });
        }
    }

    // Standard radio-group keyboard model: arrows move selection (and focus)
    // to the previous/next enabled option, wrapping; Home/End jump to the ends.
    _onKeydown(e) {
        const keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'];
        if (!keys.includes(e.key)) return;
        e.preventDefault();

        const enabled = this._options.filter((o) => !o.disabled);
        if (enabled.length === 0) return;

        let target;
        if (e.key === 'Home') {
            target = enabled[0];
        } else if (e.key === 'End') {
            target = enabled[enabled.length - 1];
        } else {
            const step = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
            const current = enabled.findIndex((o) => o.value === this.value);
            const base = current === -1 ? 0 : current;
            target = enabled[(base + step + enabled.length) % enabled.length];
        }
        this._select(target.value, { focus: true });
    }

    render() {
        const activeIndex = this._activeIndex;
        // The active layer mirrors the base layer one-for-one so the two stay
        // pixel-aligned — the clip can then split a label's colour mid-glyph.
        return html`
            <div
                class="track"
                role="radiogroup"
                aria-label=${this.accessibleLabel || nothing}
                @keydown=${this._onKeydown}
            >
                <div class="pill" aria-hidden="true"></div>
                <div class="layer layer--base">
                    ${this._options.map((option, i) => this._renderSegment(option, i, activeIndex))}
                </div>
                <div class="layer layer--active" aria-hidden="true">
                    ${this._options.map((option) => this._renderGhost(option))}
                </div>
            </div>
        `;
    }

    // The active-layer twin of a segment: same box (so widths match the real
    // button exactly) but a plain, non-interactive span in the active colour.
    _renderGhost(option) {
        return html`
            <span class="segment segment--ghost" aria-hidden="true"
            >${option.isMarkup ? unsafeHTML(option.content) : option.content}</span>
        `;
    }

    _renderSegment(option, i, activeIndex) {
        const checked = option.value === this.value;
        // Icon-only segments have no visible text, so name them with aria-label
        // and surface the same name as a hover title.
        const labelAttr = option.isMarkup ? option.accessibleLabel : nothing;
        return html`
            <button
                class="segment"
                type="button"
                role="radio"
                aria-checked=${checked ? 'true' : 'false'}
                aria-label=${labelAttr}
                title=${labelAttr}
                tabindex=${i === activeIndex ? '0' : '-1'}
                ?disabled=${this.disabled || option.disabled}
                @click=${() => this._select(option.value)}
            >${option.isMarkup ? unsafeHTML(option.content) : option.content}</button>
        `;
    }
}

customElements.define('ol-segmented-control', OlSegmentedControl);
