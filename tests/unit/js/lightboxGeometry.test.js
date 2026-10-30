import {
    NO_INSETS,
    cropInsets,
    fitRect,
    flipTransform,
    isInViewport,
    releaseVelocity,
    uncroppedRect
} from '../../../openlibrary/components/lit/utils/lightbox-geometry.js';

const viewport = { width: 1280, height: 800 };

describe('fitRect', () => {
    test('scales a large image down to fit inside the padding and centres it', () => {
        const rect = fitRect(2000, 3000, viewport, 40);
        // Height-bound: 800 - 80 = 720 tall, 2:3 → 480 wide.
        expect(rect.height).toBeCloseTo(720);
        expect(rect.width).toBeCloseTo(480);
        expect(rect.x).toBeCloseTo((1280 - 480) / 2);
        expect(rect.y).toBeCloseTo(40);
    });

    test('never upscales by default', () => {
        const rect = fitRect(300, 450, viewport, 40);
        expect(rect.width).toBe(300);
        expect(rect.height).toBe(450);
    });

    test('upscales up to maxScale, and no further', () => {
        const capped = fitRect(300, 450, viewport, 40, 1.5);
        expect(capped.width).toBeCloseTo(450);
        expect(capped.height).toBeCloseTo(675);

        // Infinity fills: height-bound at 720.
        const filled = fitRect(300, 450, viewport, 40, Infinity);
        expect(filled.height).toBeCloseTo(720);
    });
});

describe('uncroppedRect', () => {
    const box = { x: 100, y: 100, width: 120, height: 180 };

    test('is the box itself unless the image is object-fit: cover', () => {
        expect(uncroppedRect(box, 1000, 1000, 'contain')).toBe(box);
        expect(uncroppedRect(box, 0, 0, 'cover')).toBe(box);
    });

    test('a square image behind a 2:3 box is height-matched and cropped horizontally, centred', () => {
        const rect = uncroppedRect(box, 1000, 1000, 'cover');
        expect(rect.height).toBe(180);
        expect(rect.width).toBe(180);
        expect(rect.x).toBe(100 - 30);
        expect(rect.y).toBe(100);
    });

    test('a wide image behind a 2:3 box is height-matched and cropped horizontally, centred', () => {
        const rect = uncroppedRect(box, 1000, 500, 'cover');
        expect(rect.height).toBe(180);
        expect(rect.width).toBe(360);
        expect(rect.x).toBe(100 - 120);
        expect(rect.y).toBe(100);
    });

    test('a tall image behind a 2:3 box is width-matched and cropped vertically', () => {
        const rect = uncroppedRect(box, 500, 2000, 'cover');
        expect(rect.width).toBe(120);
        expect(rect.height).toBe(480);
        expect(rect.y).toBe(100 - 150);
    });

    test('object-position moves the crop window', () => {
        const top = uncroppedRect(box, 500, 2000, 'cover', '50% 0%');
        expect(top.y).toBe(100);
        const bottom = uncroppedRect(box, 500, 2000, 'cover', '50% 100%');
        expect(bottom.y).toBe(100 - 300);
    });
});

describe('cropInsets', () => {
    test('is zero when nothing is cropped', () => {
        const box = { x: 0, y: 0, width: 100, height: 150 };
        expect(cropInsets(box, box, { x: 0, y: 0, width: 400, height: 600 })).toEqual(NO_INSETS);
    });

    test('scales the hidden fraction up to the enlarged size', () => {
        const box = { x: 0, y: 50, width: 100, height: 100 };
        const uncropped = { x: 0, y: 0, width: 100, height: 200 };
        const target = { x: 0, y: 0, width: 400, height: 800 };
        // A quarter hidden top and bottom → 200px each at target size.
        expect(cropInsets(box, uncropped, target)).toEqual({ top: 200, bottom: 200, left: 0, right: 0 });
    });
});

describe('flipTransform', () => {
    const fit = { x: 400, y: 100, width: 480, height: 720 };

    test('same aspect ratio: translate centre-to-centre and scale to fit, no crop', () => {
        const thumb = { x: 100, y: 200, width: 120, height: 180 };
        const t = flipTransform(thumb, fit);
        expect(t.translateX).toBeCloseTo(160 - 640);
        expect(t.translateY).toBeCloseTo(290 - 460);
        expect(t.scale).toBeCloseTo(0.25);
        expect(t.hasCrop).toBe(false);
    });

    test('object-fit insets win: scale to fit and keep the insets', () => {
        const thumb = { x: 100, y: 200, width: 120, height: 180 };
        const insets = { top: 10, right: 0, bottom: 10, left: 0 };
        const t = flipTransform(thumb, fit, insets);
        expect(t.hasCrop).toBe(true);
        expect(t.insets).toBe(insets);
        expect(t.scale).toBeCloseTo(0.25);
    });

    test('sub-pixel insets are not a crop', () => {
        const thumb = { x: 100, y: 200, width: 120, height: 180 };
        const t = flipTransform(thumb, fit, { top: 0.3, right: 0.3, bottom: 0.2, left: 0.1 });
        expect(t.hasCrop).toBe(false);
    });

    test('an aspect mismatch fills the thumbnail and clips the excess symmetrically', () => {
        // A square thumbnail for a 2:3 image: a server-side centre crop.
        const thumb = { x: 100, y: 200, width: 120, height: 120 };
        const t = flipTransform(thumb, fit);
        expect(t.hasCrop).toBe(true);
        expect(t.scale).toBeCloseTo(0.25); // width-matched (120/480) beats height (120/720)
        expect(t.insets.left).toBe(0);
        expect(t.insets.top).toBeCloseTo((720 - 480) / 2);
        expect(t.insets.bottom).toBeCloseTo(t.insets.top);
    });
});

describe('isInViewport', () => {
    test('true when any edge is on screen, false when fully scrolled away', () => {
        expect(isInViewport({ x: -50, y: -50, width: 100, height: 100 }, viewport)).toBe(true);
        expect(isInViewport({ x: 0, y: -200, width: 100, height: 100 }, viewport)).toBe(false);
        expect(isInViewport({ x: 0, y: 900, width: 100, height: 100 }, viewport)).toBe(false);
    });
});

describe('releaseVelocity', () => {
    test('zero with fewer than two samples', () => {
        expect(releaseVelocity([])).toEqual({ vx: 0, vy: 0 });
        expect(releaseVelocity([{ x: 0, y: 0, t: 0 }])).toEqual({ vx: 0, vy: 0 });
    });

    test('px per second over the sample window', () => {
        const samples = [
            { x: 0, y: 0, t: 0 },
            { x: 0, y: 10, t: 10 },
            { x: 0, y: 20, t: 20 }
        ];
        expect(releaseVelocity(samples)).toEqual({ vx: 0, vy: 1000 });
    });

    test('ignores samples older than the window', () => {
        const samples = [
            { x: 0, y: 0, t: 0 },
            { x: 0, y: 500, t: 500 }, // a slow start, then a flick
            { x: 0, y: 520, t: 520 }
        ];
        expect(releaseVelocity(samples, 80).vy).toBe(1000);
    });
});
