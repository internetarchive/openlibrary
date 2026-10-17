import { css } from 'lit';

/**
 * Shared style fragments for the Lit controls.
 *
 * Each fragment is one opt-in class on the element that carries the look — a
 * raised fill, a press, a focus ring, a menu row — and is composed into a
 * component's `static styles` array *ahead of* its own rules, so the component
 * wins every specificity tie. Where controls legitimately differ, a fragment
 * reads one private custom property (`--_press-scale`, `--_focus-offset`) that
 * the component sets. A control that needs more than that isn't this pattern;
 * write the rule locally and say why.
 *
 *     import { raised, pressable, focusRing } from './control-styles.js';
 *     static styles = [raised, pressable, focusRing, css`...`];
 *     html`<button class="control raised pressable focus-ring">`
 */

/* The raised fill of ol-button[variant="secondary"]: a soft drop shadow plus a
   specular top edge toned to --control-surface (keep it equal to the
   background, including on hover) at --control-highlight-strength. Both are
   set by the component. The full shadow is held in --_raised-shadow so
   focusRingLayered can stack the ring on top of it. */
export const raised = css`
    .raised {
        --_raised-shadow: var(--box-shadow-raised), inset 0 1px 0 color-mix(in srgb, var(--white) var(--control-highlight-strength), var(--control-surface));
        box-shadow: var(--_raised-shadow);
    }
`;

/* Press feedback for a self-contained control. The tier follows width (see
   tokens/press.css): set --_press-scale to the compact or wide token where
   the default 3% is wrong. */
export const pressable = css`
    .pressable:active {
        transform: scale(var(--_press-scale, var(--press-scale)));
    }
`;

/* Focus ring drawn as an outline outside the box. A control inside a clipped
   container (a segment in its track, a row in its panel) sets --_focus-offset
   negative to pull the ring inside. */
export const focusRing = css`
    .focus-ring:focus-visible {
        outline: var(--focus-width) solid var(--color-focus-ring);
        outline-offset: var(--_focus-offset, var(--spacing-3xs));
    }
`;

/* Focus ring for a raised control: an outline would sit over the lift, so the
   ring is a box-shadow layered on --_raised-shadow. Requires .raised. */
export const focusRingLayered = css`
    .focus-ring-layered:focus-visible {
        outline: none;
        box-shadow: var(--box-shadow-focus), var(--_raised-shadow);
    }
`;

/* A row inside a panel — see "Menu rows" in docs/frontend/design.md. Inset
   from the panel edge so the hover fill reads as a pill, giving the inset back
   as padding; one min-height so rows line up and a described row can grow. */
export const menuRow = css`
    .menu-row {
        display: flex;
        align-items: center;
        box-sizing: border-box;
        min-height: var(--menu-row-height);
        margin-inline: var(--menu-row-inset);
        padding-block: var(--spacing-inset-xs);
        padding-inline: var(--menu-row-padding-inline);
        border-radius: var(--border-radius-menu-row);
        /* The control label weight: a menu is a stack of medium controls. */
        font-weight: var(--font-weight-button);
        line-height: var(--line-height-control);
        cursor: pointer;
    }

    @media (hover: hover) and (pointer: fine) {
        .menu-row:hover {
            background: var(--color-hover-overlay);
        }
    }

    /* The selected row takes the control-selected look on its pill: the same
       tint and link text as ol-button[selected], pagination's current page and
       the toggle's button variant. The radio, checkbox or aria-checked still
       carries the state; this only paints it. Colour and fill only, never
       weight, so nothing re-measures. Hover deepens the tint, as the button
       does, rather than greying it. */
    .menu-row[aria-checked='true'],
    .menu-row:has(> :checked) {
        background: var(--color-control-selected-bg);
        color: var(--color-link);
    }

    @media (hover: hover) and (pointer: fine) {
        .menu-row[aria-checked='true']:hover,
        .menu-row:has(> :checked):hover {
            background: var(--color-control-selected-bg-hover);
        }
    }
`;
