import { LitElement, html, css } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
// Registers <ol-button> and <ol-icon> for the close control.
import './OLButton.js';
import './OlIcon.js';
import { getDeepActiveElement } from './utils/focus-utils.js';
import { lockBodyScroll, unlockBodyScroll } from './utils/scroll-lock.js';
import { SPRING_CLOSE, SPRING_OPEN, SPRING_SETTLE, SPRING_SHRINK, SPRING_SNAP, animateSprings } from './utils/spring.js';
import { NO_INSETS, cropInsets, fitRect, flipTransform, isInViewport, releaseVelocity, uncroppedRect } from './utils/lightbox-geometry.js';

/** Pointer travel before a drag commits to an axis. */
const AXIS_LOCK_PX = 10;
/** Vertical travel must beat horizontal by this factor to read as a dismiss. */
const AXIS_LOCK_RATIO = 1.5;
/** A release this close to home, and this slow, snaps back instead of closing. */
const SNAP_BACK_DISTANCE_PX = 5;
const SNAP_BACK_SPEED = 50;
/** The image stops shrinking to a speck: it fades out between these scales. */
const SHRINK_FADE_START = 0.5;
const SHRINK_FADE_END = 0.15;
/** Below this scrim opacity the image fades too, so it hands off to a still-visible thumbnail. */
const CLOSE_IMAGE_FADE = 0.02;
/** `--width-breakpoint-tablet`; matches ol-dialog and ol-popover. */
const MOBILE_QUERY = '(max-width: 767px)';

/**
 * Enlarges an image in place: click the slotted thumbnail and it grows out of
 * its own rect into a centred, viewport-filling view; click anywhere, press
 * Escape, or swipe it away and it shrinks back to where it came from.
 *
 * Built on native `<dialog>.showModal()` like `ol-dialog` and `ol-drawer`, so
 * it sits in the top layer with no z-index, traps focus, inerts the page, and
 * shares the scrim blur. The dim is the deeper image-viewer token: the picture
 * replaces the page rather than sitting on it. The `<dialog>` fills the
 * viewport and is transparent; the scrim, the image and the close button are
 * its children.
 *
 * The morph is a FLIP: the enlarged image is laid out at its final rect, a
 * transform makes it look like the thumbnail, and a spring takes that
 * transform to identity (`utils/spring.js`, ported from Lightbox3). A spring
 * rather than the motion tokens because the close can start from a drag: the
 * release velocity feeds the animation, and a snap-back can be grabbed again
 * mid-flight. `prefers-reduced-motion` skips the motion and shows the end
 * state.
 *
 * The slot holds the trigger, normally a link to the full-size image wrapping
 * the thumbnail `<img>`, so the page still works without JavaScript and
 * modifier-clicks open the image in a new tab as the link intends.
 *
 * @element ol-lightbox
 *
 * @prop {String} src - URL of the full-size image. The thumbnail's own source
 *     is shown until it loads, so the morph starts immediately.
 * @prop {String} alt - Alternative text for the enlarged image; also names the
 *     dialog for assistive tech.
 * @prop {Boolean} open - Whether the lightbox is showing. Set it to open from
 *     code; clicking the slotted trigger sets it for you.
 * @prop {Number} upscale - Largest multiple of the image's natural size it may
 *     be drawn at. Covers are small, so the default `2` lets a 500px cover
 *     fill a laptop screen without turning a phone-sized scan to mush.
 *     Attribute: `upscale`.
 * @prop {String} labelClose - Translated accessible name for the close button.
 *     Attribute: `label-close`. Default "Close".
 *
 * @slot - The trigger: an `<a>` (or any element) containing the thumbnail `<img>`.
 *
 * @cssprop [--ol-lightbox-padding=var(--spacing-4xl)] - Minimum gap between the
 *     enlarged image and the viewport edge. `--spacing-sm` below 768px.
 * @cssprop [--ol-lightbox-image-radius=var(--border-radius-overlay)] - Corner
 *     radius of the enlarged image. It morphs from the thumbnail's own radius.
 * @cssprop [--ol-lightbox-scrim-color=var(--overlay-backdrop-color-image)] - Scrim
 *     color. Deeper than the panel scrim: the image replaces the page rather
 *     than sitting on it.
 * @cssprop [--ol-lightbox-scrim-blur=var(--overlay-backdrop-blur)] - Blur
 *     applied to the page behind the scrim. The lightbox is modal, so it blurs;
 *     see docs/frontend/design.md#blur-follows-modality-not-viewport-width.
 *
 * @fires ol-lightbox-show - Fired when the lightbox begins opening.
 * @fires ol-lightbox-after-show - Fired once the opening morph has landed.
 * @fires ol-lightbox-hide - Fired when a close is requested, before the exit.
 *     Cancelable — `event.preventDefault()` keeps it open.
 *     detail: { reason: 'escape' | 'scrim' | 'image' | 'close' | 'swipe' | 'programmatic' }
 * @fires ol-lightbox-after-hide - Fired after the exit morph completes.
 *
 * @example
 * <ol-lightbox src="/covers/123-L.jpg" alt="Cover of The Secret Garden" label-close="Close">
 *   <a href="/covers/123-L.jpg"><img src="/covers/123-M.jpg" alt="Cover of The Secret Garden"></a>
 * </ol-lightbox>
 */
export class OlLightbox extends LitElement {
    static properties = {
        src: { type: String },
        alt: { type: String },
        open: { type: Boolean, reflect: true },
        upscale: { type: Number },
        labelClose: { type: String, attribute: 'label-close' }
    };

    static styles = css`
        :host {
            --ol-lightbox-padding: var(--spacing-4xl);
            --ol-lightbox-image-radius: var(--border-radius-overlay);
            --ol-lightbox-scrim-color: var(--overlay-backdrop-color-image);
            --ol-lightbox-scrim-blur: var(--overlay-backdrop-blur);

            display: contents;
        }

        /* --width-breakpoint-tablet */
        @media (max-width: 767px) {
            :host {
                --ol-lightbox-padding: var(--spacing-sm);
            }
        }

        /* The UA stylesheet gives <dialog> fit-content sizing, a max-width, a
           border, padding, auto margins and an opaque background. Author
           styles only win for properties they declare, so every one is
           restated here (same reset as ol-drawer). */
        dialog {
            position: fixed;
            inset: 0;
            width: auto;
            height: auto;
            max-width: none;
            max-height: none;
            margin: 0;
            padding: 0;
            border: none;
            background: transparent;
            overflow: hidden;
            overflow: clip;
            /* The dialog owns every touch while open: the drag is ours, and
               there is no page to scroll behind a modal. */
            touch-action: none;
            -webkit-tap-highlight-color: transparent;
            user-select: none;
            -webkit-user-select: none;
        }

        dialog:focus {
            outline: none;
        }

        /* The scrim below is the visible dimming layer; the native backdrop
           would sit underneath the viewport-filling dialog and never show. */
        dialog::backdrop {
            background: transparent;
        }

        /* Same blur as ol-dialog and ol-drawer, deeper dim. Its opacity is set from JS
           every frame — by the opening spring and then by the drag — which
           is why it is an element and not ::backdrop. The blur is constant
           and rides on the opacity. */
        .scrim {
            position: absolute;
            inset: 0;
            background: var(--ol-lightbox-scrim-color);
            opacity: 0;
            backdrop-filter: blur(var(--ol-lightbox-scrim-blur));
            -webkit-backdrop-filter: blur(var(--ol-lightbox-scrim-blur));
        }

        /* Laid out at its fit rect by JS; only transform, clip-path and
           border-radius change per frame. A sibling of the scrim, never a
           child: backdrop-filter would make the scrim its containing block. */
        .image {
            position: absolute;
            display: block;
            transform-origin: center center;
            will-change: transform;
            border-radius: var(--ol-lightbox-image-radius);
            box-shadow: var(--box-shadow-overlay);
            -webkit-user-drag: none;
            cursor: zoom-out;
        }

        .close-button {
            position: absolute;
            inset-block-start: var(--spacing-lg);
            inset-inline-end: var(--spacing-lg);
        }

        /* Resolves the two length tokens to px for the geometry: a custom
           property reads back unresolved ("2.5rem"), a computed width doesn't. */
        .probe {
            position: absolute;
            visibility: hidden;
            pointer-events: none;
            width: var(--ol-lightbox-padding);
            height: var(--ol-lightbox-image-radius);
        }
    `;

    constructor() {
        super();
        this.src = '';
        this.alt = '';
        this.open = false;
        this.upscale = 2;
        this.labelClose = 'Close';

        /** @type {HTMLElement|null} Element that had focus before the lightbox opened */
        this._previouslyFocusedElement = null;
        /** @type {boolean} Whether this lightbox currently holds a body scroll lock */
        this._scrollLocked = false;
        /** Bumped on every open and close so a stale callback can bow out. */
        this._cycle = 0;
        /** @type {'programmatic' | 'escape' | 'scrim' | 'image' | 'close' | 'swipe'} */
        this._closeReason = 'programmatic';

        /** True from show() until the opening morph has visually landed. */
        this._opening = false;
        /** True from hide() until the dialog is actually closed. */
        this._closing = false;
        /** @type {{ cancel: () => void, current: Object }|null} The running spring loop, if any */
        this._animation = null;
        /** @type {{ cancel: () => void }|null} The post-load rect settle, if any */
        this._settle = null;

        /** Live values of the last painted frame; a close starts from here. */
        this._frame = { translateX: 0, translateY: 0, scale: 1, opacity: 0, crop: 0, radius: 0 };
        /** Clip insets, in enlarged-image pixels, scaled by `_frame.crop`. */
        this._insets = NO_INSETS;
        /** @type {import('./utils/lightbox-geometry.js').Rect|null} Where the enlarged image is laid out */
        this._fitRect = null;
        this._natural = { width: 0, height: 0 };
        this._thumbRadius = 0;
        this._targetRadius = 0;
        /** Set while shrinking into the centre, which fades the image rather than the scrim. */
        this._shrinking = false;
        /** Set while a swipe-dismiss close is running: the image stays visible to the thumbnail. */
        this._dismissClosing = false;

        /** @type {HTMLImageElement|null} The full-size image, preloaded on hover/focus */
        this._fullImage = null;

        // Drag state (vertical swipe-to-dismiss)
        this._drag = this._idleDrag();
        /** @type {{ x: number, y: number, t: number }[]} */
        this._velocitySamples = [];

        this._onTriggerClick = this._onTriggerClick.bind(this);
        this._warmFullImage = this._warmFullImage.bind(this);
        this._onPointerDown = this._onPointerDown.bind(this);
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
        this._onKeyDown = this._onKeyDown.bind(this);
        this._onResize = this._onResize.bind(this);
        this._onCancel = this._onCancel.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('click', this._onTriggerClick);
        this.addEventListener('pointerover', this._warmFullImage);
        this.addEventListener('focusin', this._warmFullImage);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('click', this._onTriggerClick);
        this.removeEventListener('pointerover', this._warmFullImage);
        this.removeEventListener('focusin', this._warmFullImage);
        this._detachOpenListeners();
        this._animation?.cancel();
        this._settle?.cancel();
        // Safety net: if torn down while open, don't leave the body pinned.
        this._releaseScrollLock();
    }

    render() {
        return html`
            <slot></slot>
            <dialog
                aria-modal="true"
                aria-label=${ifDefined(this.alt || undefined)}
                @cancel=${this._onCancel}
                @pointerdown=${this._onPointerDown}
                @pointermove=${this._onPointerMove}
                @pointerup=${this._onPointerUp}
                @pointercancel=${this._onPointerUp}
            >
                <div class="scrim"></div>
                <div class="probe"></div>
                <img class="image" alt=${this.alt} draggable="false" decoding="async" />
                <ol-button class="close-button" shape="circle" elevation="floating" aria-label=${this.labelClose} @click=${this._onCloseClick}>
                    <ol-icon name="x"></ol-icon>
                </ol-button>
            </dialog>
        `;
    }

    /** @returns {HTMLDialogElement} */
    get dialog() {
        return this.renderRoot?.querySelector('dialog');
    }

    /** @returns {HTMLImageElement} */
    get _image() {
        return this.renderRoot?.querySelector('.image');
    }

    /** @returns {HTMLElement} */
    get _scrim() {
        return this.renderRoot?.querySelector('.scrim');
    }

    /** @returns {HTMLElement} */
    get _closeButton() {
        return this.renderRoot?.querySelector('.close-button');
    }

    /** @returns {HTMLImageElement|null} The slotted thumbnail the morph starts from and returns to. */
    get _thumb() {
        return this.querySelector('img');
    }

    updated(changedProperties) {
        if (changedProperties.has('open')) {
            if (this.open) {
                this._show();
            } else if (changedProperties.get('open') === true) {
                this._hide();
            }
        }
        if (changedProperties.has('src') && changedProperties.get('src') !== undefined) {
            // A new full-size image (e.g. after a cover upload): forget the old preload.
            this._fullImage = null;
        }
    }

    // ── Trigger ────────────────────────────────────────────────

    _onTriggerClick(event) {
        // Clicks inside the dialog (the close button) reach the host too.
        if (event.composedPath().includes(this.dialog)) return;
        // Leave modifier and non-primary clicks to the link: open in a new tab.
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
        event.preventDefault();
        this.open = true;
    }

    /** Start the full-size download on the first hover or focus, so it is often ready by the click. */
    _warmFullImage() {
        if (this._fullImage || !this.src) return;
        const image = new Image();
        image.decoding = 'async';
        image.src = this.src;
        this._fullImage = image;
    }

    /** @returns {boolean} Whether the preloaded full-size image has its dimensions. */
    get _fullImageReady() {
        const image = this._fullImage;
        return !!image && image.complete && image.naturalWidth > 0;
    }

    // ── Show / Hide ─────────────────────────────────────────────

    _show() {
        const dialog = this.dialog;
        const image = this._image;
        const thumb = this._thumb;
        if (!dialog || !image) return;

        // Reopened during the exit morph: showModal() is still in effect.
        const reopening = dialog.open;
        const cycle = ++this._cycle;
        this._animation?.cancel();
        this._settle?.cancel();
        this._closing = false;
        this._shrinking = false;
        this._dismissClosing = false;
        this._drag = this._idleDrag();
        image.style.opacity = '';

        if (!reopening) {
            this._previouslyFocusedElement = getDeepActiveElement();
        }

        this.dispatchEvent(new CustomEvent('ol-lightbox-show', { bubbles: true, composed: true }));

        // Calling showModal() on an open dialog throws.
        if (!reopening) dialog.showModal();

        // showModal() blocks background scroll on desktop but not touch-scroll
        // on iOS Safari, so pin <body> as well.
        if (!this._scrollLocked) {
            lockBodyScroll();
            this._scrollLocked = true;
        }

        this._attachOpenListeners();
        this._warmFullImage();

        const viewport = this._viewport();
        const thumbRect = thumb ? this._measureThumb(thumb) : null;
        const fromCenter = !thumbRect || thumbRect.width === 0 || thumbRect.height === 0 || !isInViewport(thumbRect, viewport);

        // The full-size dimensions decide the fit rect. Unknown until it loads,
        // so fill the viewport on the thumbnail's aspect ratio and settle to
        // the real rect when the image arrives — usually invisible, since
        // covers rarely reach the upscale cap on a laptop screen.
        let natural;
        let fit;
        if (this._fullImageReady) {
            natural = { width: this._fullImage.naturalWidth, height: this._fullImage.naturalHeight };
            fit = fitRect(natural.width, natural.height, viewport, this._padding(), this._maxScale());
            image.src = this.src;
        } else {
            const width = thumb?.naturalWidth || thumbRect?.width || 2;
            const height = thumb?.naturalHeight || thumbRect?.height || 3;
            natural = { width, height };
            fit = fitRect(width, height, viewport, this._padding(), Infinity);
            image.src = thumb?.currentSrc || thumb?.src || this.src;
            this._swapToFullImage(cycle);
        }
        this._natural = natural;
        this._fitRect = fit;
        this._positionImage(fit);

        this._thumbRadius = thumb ? this._borderRadiusOf(thumb) : 0;
        this._targetRadius = this._probe().radius;

        let morph;
        if (fromCenter) {
            morph = { translateX: 0, translateY: 0, scale: 0, hasCrop: false, insets: NO_INSETS };
        } else {
            const box = thumb.getBoundingClientRect();
            morph = flipTransform(thumbRect, fit, cropInsets(box, thumbRect, fit));
        }
        this._insets = morph.insets;

        this._setThumbVisibility(false);
        this._opening = true;

        this._animate({
            from: {
                translateX: morph.translateX,
                translateY: morph.translateY,
                scale: morph.scale,
                opacity: 0,
                crop: morph.hasCrop ? 1 : 0,
                radius: this._thumbRadius
            },
            to: { translateX: 0, translateY: 0, scale: 1, opacity: 1, crop: 0, radius: this._targetRadius },
            config: SPRING_OPEN,
            // Visually open well before the spring settles: unblock the drag
            // and tell listeners, while the overshoot finishes on its own.
            onFrame: frame => {
                if (this._opening && frame.opacity > 0.99) this._landed(cycle);
            }
        });
    }

    _landed(cycle) {
        if (cycle !== this._cycle) return;
        this._opening = false;
        this.dispatchEvent(new CustomEvent('ol-lightbox-after-show', { bubbles: true, composed: true }));
    }

    /** Once the full-size image loads, show it and ease the rect to its true size if that differs. */
    _swapToFullImage(cycle) {
        const image = this._fullImage;
        if (!image) return;
        const apply = () => {
            if (cycle !== this._cycle || this._closing || !this.dialog?.open) return;
            if (!image.naturalWidth) return;
            this._image.src = this.src;
            this._natural = { width: image.naturalWidth, height: image.naturalHeight };
            const target = fitRect(this._natural.width, this._natural.height, this._viewport(), this._padding(), this._maxScale());
            this._settleTo(target);
        };
        if (this._fullImageReady) {
            apply();
        } else {
            image.addEventListener('load', apply, { once: true });
        }
    }

    /** Spring the laid-out rect to `target` when it differs from the current one by more than a pixel. */
    _settleTo(target) {
        const from = this._fitRect;
        const moved =
            Math.abs(target.x - from.x) > 1 ||
            Math.abs(target.y - from.y) > 1 ||
            Math.abs(target.width - from.width) > 1 ||
            Math.abs(target.height - from.height) > 1;
        if (!moved) return;
        this._settle?.cancel();
        if (this._reducedMotion) {
            this._fitRect = target;
            this._positionImage(target);
            return;
        }
        this._settle = animateSprings({
            from: { x: from.x, y: from.y, width: from.width, height: from.height },
            to: target,
            config: SPRING_SETTLE,
            onFrame: rect => {
                this._fitRect = { ...rect };
                this._positionImage(rect);
            },
            onDone: () => {
                this._settle = null;
            }
        });
    }

    _hide() {
        const dialog = this.dialog;
        if (!dialog || !dialog.open) return;

        const reason = this._closeReason;
        this._closeReason = 'programmatic';

        const hideEvent = new CustomEvent('ol-lightbox-hide', {
            bubbles: true,
            composed: true,
            cancelable: true,
            detail: { reason }
        });
        this.dispatchEvent(hideEvent);
        if (hideEvent.defaultPrevented) {
            this.open = true;
            return;
        }

        const cycle = ++this._cycle;
        this._opening = false;
        this._closing = true;
        this._dismissClosing = reason === 'swipe';
        this._detachOpenListeners();
        this._animation?.cancel();
        this._settle?.cancel();

        const velocity = this._drag.active ? releaseVelocity(this._velocitySamples) : { vx: 0, vy: 0 };
        this._drag = this._idleDrag();

        const viewport = this._viewport();
        const thumb = this._thumb;
        const thumbRect = thumb ? this._measureThumb(thumb) : null;
        const from = { ...this._frame };
        const finish = () => this._finishClose(cycle);

        // Nothing to return to: shrink into the centre and fade.
        if (!thumbRect || !isInViewport(thumbRect, viewport)) {
            this._shrinking = true;
            this._animate({
                from,
                to: { translateX: 0, translateY: 0, scale: 0, opacity: 0, crop: 0, radius: from.radius },
                config: SPRING_SHRINK,
                velocity: { translateX: velocity.vx, translateY: velocity.vy },
                doneWhen: s => s.opacity < 0.01 && s.scale < SHRINK_FADE_END,
                onDone: finish
            });
            return;
        }

        const fit = this._fitRect;
        const morph = flipTransform(thumbRect, fit, cropInsets(thumb.getBoundingClientRect(), thumbRect, fit));
        this._insets = morph.insets;

        // A fling curves toward the thumbnail: the axis carrying more velocity
        // gets a softer spring, so momentum carries it while the other axis
        // converges first.
        let configs;
        const absVx = Math.abs(velocity.vx);
        const absVy = Math.abs(velocity.vy);
        const ratio = Math.max(absVx, absVy) / (Math.min(absVx, absVy) || 1);
        if (ratio > 1.5 && Math.max(absVx, absVy) > 100) {
            const soft = { ...SPRING_CLOSE, stiffness: SPRING_CLOSE.stiffness * 0.55, damping: SPRING_CLOSE.damping * 0.85 };
            configs = absVy > absVx ? { translateY: soft } : { translateX: soft };
        }

        // After a drag the scrim may already be near zero, so "invisible" is
        // not enough: finish when the image sits on the thumbnail, with
        // tolerance for the overshoot of a fast flick.
        const atThumbnail = s =>
            Math.abs(s.scale - morph.scale) < 0.05 && Math.abs(s.translateX - morph.translateX) < 20 && Math.abs(s.translateY - morph.translateY) < 20;

        this._animate({
            from,
            to: {
                translateX: morph.translateX,
                translateY: morph.translateY,
                scale: morph.scale,
                opacity: 0,
                crop: morph.hasCrop ? 1 : 0,
                radius: this._thumbRadius
            },
            config: SPRING_CLOSE,
            configs,
            velocity: { translateX: velocity.vx, translateY: velocity.vy },
            doneWhen: s => (this._dismissClosing ? atThumbnail(s) : s.opacity < 0.01),
            onDone: finish
        });
    }

    _finishClose(cycle) {
        if (cycle !== this._cycle) return;
        const dialog = this.dialog;
        this._animation = null;
        this._closing = false;
        this._shrinking = false;
        this._dismissClosing = false;
        this._setThumbVisibility(true);
        this._clearImageStyles();
        dialog?.close();
        this._releaseScrollLock();
        this._restoreFocus();
        this.dispatchEvent(new CustomEvent('ol-lightbox-after-hide', { bubbles: true, composed: true }));
    }

    // ── Animation ───────────────────────────────────────────────

    get _reducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    /**
     * Run the morph springs, or jump to the end state under reduced motion.
     * @param {Parameters<typeof animateSprings>[0]} options
     */
    _animate({ from, to, config, velocity, configs, onFrame, onDone, doneWhen }) {
        this._animation?.cancel();
        const paint = frame => {
            this._applyFrame(frame);
            onFrame?.(frame);
        };
        if (this._reducedMotion) {
            paint({ ...from, ...to });
            this._animation = null;
            onDone?.();
            return;
        }
        this._animation = animateSprings({
            from,
            to,
            config,
            velocity,
            configs,
            onFrame: paint,
            doneWhen,
            onDone: () => {
                this._animation = null;
                onDone?.();
            }
        });
    }

    /** Paint one frame of the morph onto the image, scrim and close button. */
    _applyFrame(frame) {
        const image = this._image;
        const scrim = this._scrim;
        const closeButton = this._closeButton;
        if (!image || !scrim) return;
        Object.assign(this._frame, frame);
        const { translateX, translateY, scale, opacity, crop, radius } = this._frame;

        image.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
        scrim.style.opacity = String(opacity);

        if (this._shrinking) {
            const t = (scale - SHRINK_FADE_END) / (SHRINK_FADE_START - SHRINK_FADE_END);
            image.style.opacity = String(Math.min(1, Math.max(0, t)));
        } else if (this._closing && !this._dismissClosing && this._isMobile()) {
            // The thumbnail stays visible on phones, so fade the image in the
            // final stretch to ease the handoff rather than snapping away.
            image.style.opacity = opacity < CLOSE_IMAGE_FADE ? String(opacity / CLOSE_IMAGE_FADE) : '';
        } else {
            image.style.opacity = '';
        }

        // The radius is divided by the scale so its *visual* size is the
        // animated value while the element is scaled down.
        const visualRadius = radius > 0.1 ? radius / Math.max(scale, 0.01) : 0;
        if (crop > 0.001) {
            const { top, right, bottom, left } = this._insets;
            image.style.clipPath = `inset(${crop * top}px ${crop * right}px ${crop * bottom}px ${crop * left}px round ${visualRadius}px)`;
            image.style.borderRadius = '';
        } else {
            image.style.clipPath = '';
            image.style.borderRadius = visualRadius > 0.1 ? `${visualRadius}px` : '';
        }

        if (closeButton) {
            // The close button rides the scrim; on the way out it leaves ahead of the image.
            closeButton.style.opacity = String(this._closing ? opacity * opacity : opacity);
            closeButton.style.pointerEvents = opacity > 0.5 ? '' : 'none';
        }
    }

    _clearImageStyles() {
        const image = this._image;
        if (image) {
            image.style.transform = '';
            image.style.clipPath = '';
            image.style.borderRadius = '';
            image.style.opacity = '';
            image.removeAttribute('src');
        }
        const scrim = this._scrim;
        if (scrim) scrim.style.opacity = '0';
        this._frame = { translateX: 0, translateY: 0, scale: 1, opacity: 0, crop: 0, radius: 0 };
        this._insets = NO_INSETS;
    }

    // ── Geometry ────────────────────────────────────────────────

    _viewport() {
        return { width: window.innerWidth, height: window.innerHeight };
    }

    _isMobile() {
        return window.matchMedia(MOBILE_QUERY).matches;
    }

    _padding() {
        return this._probe().width;
    }

    /** The padding and image-radius tokens, resolved to px. */
    _probe() {
        const probe = this.renderRoot?.querySelector('.probe');
        if (!probe) return { width: 0, radius: 0 };
        const style = getComputedStyle(probe);
        return { width: parseFloat(style.width) || 0, radius: parseFloat(style.height) || 0 };
    }

    /** The `upscale` cap as a scale factor; junk values (0, negative, NaN) mean "never upscale". */
    _maxScale() {
        return this.upscale > 1 ? this.upscale : 1;
    }

    /** @param {HTMLImageElement} thumb */
    _measureThumb(thumb) {
        const style = getComputedStyle(thumb);
        const box = thumb.getBoundingClientRect();
        return uncroppedRect(
            { x: box.x, y: box.y, width: box.width, height: box.height },
            thumb.naturalWidth,
            thumb.naturalHeight,
            style.objectFit,
            style.objectPosition
        );
    }

    /** @param {HTMLElement} el */
    _borderRadiusOf(el) {
        return parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
    }

    /** @param {import('./utils/lightbox-geometry.js').Rect} rect */
    _positionImage(rect) {
        const image = this._image;
        if (!image) return;
        Object.assign(image.style, {
            left: `${rect.x}px`,
            top: `${rect.y}px`,
            width: `${rect.width}px`,
            height: `${rect.height}px`
        });
    }

    /** Hide the thumbnail while the enlarged image stands in for it. Phones keep it: the morph is short there and the handoff fades instead. */
    _setThumbVisibility(visible) {
        const thumb = this._thumb;
        if (!thumb) return;
        if (!visible && this._isMobile()) return;
        thumb.style.visibility = visible ? '' : 'hidden';
    }

    _onResize() {
        if (this._closing || !this._fitRect) return;
        this._settle?.cancel();
        this._settle = null;
        const fit = fitRect(this._natural.width, this._natural.height, this._viewport(), this._padding(), this._fullImageReady ? this._maxScale() : Infinity);
        this._fitRect = fit;
        this._positionImage(fit);
    }

    // ── Listeners held while open ───────────────────────────────

    _attachOpenListeners() {
        // Capture phase to intercept Tab before Safari's native handling.
        document.addEventListener('keydown', this._onKeyDown, true);
        window.addEventListener('resize', this._onResize);
    }

    _detachOpenListeners() {
        document.removeEventListener('keydown', this._onKeyDown, true);
        window.removeEventListener('resize', this._onResize);
    }

    /**
     * The close button is the only tab stop, so Tab and Shift+Tab both land
     * on it. Enforced by hand because Safari lets Tab leave a shadow
     * `<dialog>` even under showModal().
     */
    _onKeyDown(event) {
        if (event.key !== 'Tab') return;
        event.preventDefault();
        this._closeButton?.focus();
    }

    // ── Dismiss handlers ────────────────────────────────────────

    /** Native dialog cancel event (Escape key). */
    _onCancel(event) {
        // Prevent the native close so we can animate the exit.
        event.preventDefault();
        if (this._closing) return;
        this._requestClose('escape');
    }

    _onCloseClick(event) {
        event.stopPropagation();
        this._requestClose('close');
    }

    /** @param {'escape' | 'scrim' | 'image' | 'close' | 'swipe'} reason */
    _requestClose(reason) {
        this._closeReason = reason;
        this.open = false;
    }

    // ── Pointer: click-to-close and swipe-to-dismiss ────────────

    _idleDrag() {
        return { tracking: false, active: false, pointerId: null, onImage: false, startX: 0, startY: 0, offsetX: 0, offsetY: 0 };
    }

    _onPointerDown(event) {
        if (event.composedPath().includes(this._closeButton)) return;
        if (this._closing || this._opening) return;
        // A second finger (pinch) is not a drag.
        if (this._drag.tracking || this._drag.active) return;
        event.preventDefault();

        // Capture on the dialog so move/up events keep arriving off the image.
        try {
            this.dialog.setPointerCapture(event.pointerId);
        } catch {
            // Synthetic events carry no capturable pointer; the handlers still work.
        }

        // Grabbing a snap-back mid-flight is allowed: continue from where it is.
        this._animation?.cancel();
        this._animation = null;

        this._drag = {
            ...this._idleDrag(),
            tracking: true,
            pointerId: event.pointerId,
            onImage: event.composedPath().includes(this._image),
            startX: event.clientX - this._frame.translateX,
            startY: event.clientY - this._frame.translateY
        };
        this._velocitySamples = [];
        this._addVelocitySample(event);
    }

    _onPointerMove(event) {
        const drag = this._drag;
        if (!drag.tracking && !drag.active) return;
        if (event.pointerId !== drag.pointerId) return;

        const dx = event.clientX - drag.startX;
        const dy = event.clientY - drag.startY;

        if (!drag.active) {
            if (Math.hypot(dx, dy) < AXIS_LOCK_PX) return;
            if (Math.abs(dy) > Math.abs(dx) * AXIS_LOCK_RATIO) {
                drag.active = true;
                drag.tracking = false;
            } else {
                // A sideways drag is nothing here: no gallery to swipe through.
                this._drag = this._idleDrag();
                this._snapHome();
                return;
            }
        }

        this._addVelocitySample(event);
        drag.offsetX = dx;
        drag.offsetY = dy;

        // Scale and scrim follow the distance from home.
        const progress = Math.hypot(dx, dy) / window.innerHeight;
        this._applyFrame({
            translateX: dx,
            translateY: dy,
            scale: Math.max(0.7, 1 - progress * 0.3),
            opacity: Math.max(0, 1 - progress / 0.4)
        });
    }

    _onPointerUp(event) {
        const drag = this._drag;
        if (!drag.tracking && !drag.active) return;
        if (event.pointerId !== drag.pointerId) return;

        try {
            this.dialog.releasePointerCapture(event.pointerId);
        } catch {
            // Already released, or never captured.
        }

        // A press with no drag is a click: anywhere closes.
        if (!drag.active) {
            const reason = drag.onImage ? 'image' : 'scrim';
            this._drag = this._idleDrag();
            if (event.type === 'pointercancel') {
                this._snapHome();
            } else {
                this._requestClose(reason);
            }
            return;
        }

        // A sample at the release itself, so a finger that stopped and held
        // before lifting reads as still, not as its last flick.
        this._addVelocitySample(event);
        const { vx, vy } = releaseVelocity(this._velocitySamples);
        const distance = Math.hypot(drag.offsetX, drag.offsetY);
        const speed = Math.hypot(vx, vy);

        // Dismiss is the default once the gesture is live, as in a native
        // photo viewer; only a deliberate return to centre snaps back.
        if (distance < SNAP_BACK_DISTANCE_PX && speed < SNAP_BACK_SPEED) {
            this._drag = this._idleDrag();
            this._snapHome({ vx, vy });
            return;
        }

        // `_hide` reads the live drag state and release velocity.
        this._requestClose('swipe');
    }

    /**
     * Spring the image back to its resting pose: after an abandoned drag, or
     * a touch that cancelled an animation (the open overshoot, an earlier
     * snap-back) and then went nowhere.
     * @param {{ vx: number, vy: number }} [velocity]
     */
    _snapHome(velocity = { vx: 0, vy: 0 }) {
        const { translateX, translateY, scale, opacity } = this._frame;
        if (translateX === 0 && translateY === 0 && scale === 1 && opacity === 1 && !velocity.vx && !velocity.vy) return;
        this._animate({
            from: { ...this._frame },
            to: { translateX: 0, translateY: 0, scale: 1, opacity: 1, crop: 0, radius: this._targetRadius },
            config: SPRING_SNAP,
            velocity: { translateX: velocity.vx, translateY: velocity.vy }
        });
    }

    _addVelocitySample(event) {
        this._velocitySamples.push({ x: event.clientX, y: event.clientY, t: performance.now() });
        if (this._velocitySamples.length > 10) this._velocitySamples.shift();
    }

    // ── Cleanup ─────────────────────────────────────────────────

    /** Releases the body scroll lock if this lightbox holds one. Idempotent. */
    _releaseScrollLock() {
        if (this._scrollLocked) {
            unlockBodyScroll();
            this._scrollLocked = false;
        }
    }

    _restoreFocus() {
        if (this._previouslyFocusedElement && typeof this._previouslyFocusedElement.focus === 'function') {
            // setTimeout so focus lands after the dialog is fully closed.
            setTimeout(() => {
                this._previouslyFocusedElement?.focus({ preventScroll: true });
                this._previouslyFocusedElement = null;
            }, 0);
        }
    }
}

if (!customElements.get('ol-lightbox')) {
    customElements.define('ol-lightbox', OlLightbox);
}
