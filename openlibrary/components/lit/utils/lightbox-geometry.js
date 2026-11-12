/**
 * The rect maths behind `ol-lightbox`'s FLIP morph, kept DOM-free so it can be
 * unit-tested. Ported from Lightbox3 (github.com/lokesh/lightbox3, MIT).
 *
 * The morph works in viewport coordinates: the enlarged image is laid out at
 * its final "fit" rect, then a transform makes it look like it is sitting at
 * the thumbnail's rect, and a spring takes that transform to identity.
 */

/**
 * @typedef {Object} Rect
 * @prop {number} x
 * @prop {number} y
 * @prop {number} width
 * @prop {number} height
 */

/**
 * @typedef {Object} Insets
 * @prop {number} top
 * @prop {number} right
 * @prop {number} bottom
 * @prop {number} left
 */

/** @type {Insets} */
export const NO_INSETS = Object.freeze({ top: 0, right: 0, bottom: 0, left: 0 });

/**
 * Where an image of `naturalWidth`×`naturalHeight` lands when centred in the
 * viewport, inset by `padding`: scaled down to fit, and up by at most
 * `maxScale` times its natural size (1 never upscales, `Infinity` always fills).
 *
 * @param {number} naturalWidth
 * @param {number} naturalHeight
 * @param {{ width: number, height: number }} viewport
 * @param {number} padding
 * @param {number} [maxScale=1]
 * @returns {Rect}
 */
export function fitRect(naturalWidth, naturalHeight, viewport, padding, maxScale = 1) {
    const scale = Math.min((viewport.width - padding * 2) / naturalWidth, (viewport.height - padding * 2) / naturalHeight, maxScale);
    const width = naturalWidth * scale;
    const height = naturalHeight * scale;
    return { x: (viewport.width - width) / 2, y: (viewport.height - height) / 2, width, height };
}

/**
 * The rect the *whole* image occupies behind an `object-fit: cover` box. The
 * box crops the image, so morphing from the box's rect would start at the
 * wrong aspect ratio and jitter; this is the uncropped rect the box is a
 * window onto. For any other `object-fit` it is the box itself.
 *
 * @param {Rect} boxRect - The `<img>` element's rect.
 * @param {number} naturalWidth
 * @param {number} naturalHeight
 * @param {string} objectFit - The computed `object-fit`.
 * @param {string} [objectPosition='50% 50%'] - The computed `object-position`.
 * @returns {Rect}
 */
export function uncroppedRect(boxRect, naturalWidth, naturalHeight, objectFit, objectPosition = '50% 50%') {
    if (objectFit !== 'cover' || !naturalWidth || !naturalHeight) return boxRect;

    const natRatio = naturalWidth / naturalHeight;
    const boxRatio = boxRect.width / boxRect.height;

    let width, height;
    if (natRatio > boxRatio) {
        height = boxRect.height;
        width = boxRect.height * natRatio;
    } else {
        width = boxRect.width;
        height = boxRect.width / natRatio;
    }

    const [px, py] = parseObjectPosition(objectPosition);
    return {
        x: boxRect.x + (boxRect.width - width) * px,
        y: boxRect.y + (boxRect.height - height) * py,
        width,
        height
    };
}

/** @returns {[number, number]} Fractions along x and y; keywords and lengths fall back to centre. */
function parseObjectPosition(value) {
    const parts = value.trim().split(/\s+/);
    const frac = part => (part?.endsWith('%') ? parseFloat(part) / 100 : 0.5);
    return [frac(parts[0]), frac(parts[1])];
}

/**
 * How much of `uncropped` is hidden by the cropping `box`, expressed as pixel
 * insets on the enlarged image at `target` size — the `clip-path: inset()`
 * that makes the enlarged image match the cropped thumbnail at the start of
 * the morph.
 *
 * @param {Rect} box
 * @param {Rect} uncropped
 * @param {Rect} target
 * @returns {Insets}
 */
export function cropInsets(box, uncropped, target) {
    const topFrac = Math.max(0, box.y - uncropped.y) / uncropped.height;
    const leftFrac = Math.max(0, box.x - uncropped.x) / uncropped.width;
    const bottomFrac = Math.max(0, uncropped.y + uncropped.height - (box.y + box.height)) / uncropped.height;
    const rightFrac = Math.max(0, uncropped.x + uncropped.width - (box.x + box.width)) / uncropped.width;
    return {
        top: topFrac * target.height,
        right: rightFrac * target.width,
        bottom: bottomFrac * target.height,
        left: leftFrac * target.width
    };
}

/**
 * The transform that makes an image laid out at `fit` look like it sits at
 * `morph` (the thumbnail), plus any crop needed to hide the difference in
 * aspect ratio.
 *
 * Three cases, in order:
 * 1. The thumbnail crops with `object-fit: cover` (`insets` is non-zero):
 *    scale to fit and clip by the insets.
 * 2. The two rects differ in aspect ratio by more than 5% (a server-side
 *    crop): scale to *fill* the thumbnail and clip the excess symmetrically.
 * 3. Same aspect ratio: scale to fit, no clip.
 *
 * `translateX`/`translateY` are centre-to-centre, for `transform-origin: center`.
 *
 * @param {Rect} morph - Where the image should appear to be (thumbnail rect).
 * @param {Rect} fit - Where the image is laid out (its enlarged rect).
 * @param {Insets} [insets=NO_INSETS] - From {@link cropInsets}, when the thumbnail is `object-fit: cover`.
 * @returns {{ translateX: number, translateY: number, scale: number, hasCrop: boolean, insets: Insets }}
 */
export function flipTransform(morph, fit, insets = NO_INSETS) {
    const translateX = morph.x + morph.width / 2 - (fit.x + fit.width / 2);
    const translateY = morph.y + morph.height / 2 - (fit.y + fit.height / 2);
    const scaleX = morph.width / fit.width;
    const scaleY = morph.height / fit.height;

    // Sub-pixel noise from rect measurement isn't a crop.
    if (insets.top + insets.right + insets.bottom + insets.left > 1) {
        return { translateX, translateY, scale: Math.min(scaleX, scaleY), hasCrop: true, insets };
    }

    const morphRatio = morph.width / morph.height;
    const fitRatio = fit.width / fit.height;
    const relDiff = Math.abs(morphRatio - fitRatio) / Math.max(morphRatio, fitRatio);
    if (relDiff > 0.05) {
        const scale = Math.max(scaleX, scaleY);
        const visibleW = morph.width / scale;
        const visibleH = morph.height / scale;
        const block = Math.max(0, (fit.height - visibleH) / 2);
        const inline = Math.max(0, (fit.width - visibleW) / 2);
        return { translateX, translateY, scale, hasCrop: true, insets: { top: block, bottom: block, left: inline, right: inline } };
    }

    return { translateX, translateY, scale: Math.min(scaleX, scaleY), hasCrop: false, insets: NO_INSETS };
}

/**
 * Whether any part of `rect` is on screen.
 *
 * @param {Rect} rect
 * @param {{ width: number, height: number }} viewport
 * @returns {boolean}
 */
export function isInViewport(rect, viewport) {
    return rect.y + rect.height > 0 && rect.y < viewport.height && rect.x + rect.width > 0 && rect.x < viewport.width;
}

/**
 * Release velocity from the last `windowMs` of pointer samples, in px/s.
 *
 * @param {{ x: number, y: number, t: number }[]} samples - Oldest first.
 * @param {number} [windowMs=80]
 * @returns {{ vx: number, vy: number }}
 */
export function releaseVelocity(samples, windowMs = 80) {
    if (samples.length < 2) return { vx: 0, vy: 0 };
    const last = samples[samples.length - 1];
    let first = samples[0];
    for (const sample of samples) {
        if (last.t - sample.t <= windowMs) {
            first = sample;
            break;
        }
    }
    const dt = (last.t - first.t) / 1000;
    if (dt <= 0) return { vx: 0, vy: 0 };
    return { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
}
