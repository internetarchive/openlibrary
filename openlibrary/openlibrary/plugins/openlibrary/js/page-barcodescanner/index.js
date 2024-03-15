// @ts-check
import countBy from 'lodash/countBy';
import maxBy from 'lodash/maxBy';
import Quagga from '@ericblade/quagga2';  // barcode scanning library
import LazyBookCard from './LazyBookCard';
import OCRScanner from './OCRScanner';

const BOX_STYLE = {color: 'green', lineWidth: 2};
const RESULT_BOX_STYLE = {color: 'blue', lineWidth: 2};
const RESULT_LINE_STYLE = {color: 'red', lineWidth: 15};

class OLBarcodeScanner {
    constructor() {
        this.lastISBN = null;

        const urlParams = new URLSearchParams(location.search)
        this.returnTo = urlParams.get('returnTo');

        this.clearOverlays = this.clearOverlays.bind(this);

        // If we get noise, group and choose latest
        this.submitISBNThrottled = new ThrottleGrouping({
            func: this.submitISBN.bind(this),
            // Use the most frequent
            reducer: (groupOfAargs) => {
                const isbnCounts = Array.from(
                    Object.entries(
                        countBy(groupOfAargs, (arg) => arg[0])
                    )
                );

                /* eslint-disable no-unused-vars */
                const mostFrequentISBN = maxBy(isbnCounts, ([isbn, count]) => count)[0];
                return groupOfAargs.reverse().find((args) => args[0] === mostFrequentISBN);
            },
            wait: 300,
        }).asFunction();
    }

    start() {
        Quagga.init({
            locator: {
                halfSample: true,
            },
            inputStream: {
                name: 'Live',
                type: 'LiveStream',
                target: $('#interactive')[0],
                constraints: {
                    // Vertical - This is *essential* for iPhone/iPad
                    aspectRatio: {ideal: 720/1280},
                },
            },
            decoder: {
                readers: ['ean_reader']
            },
        }, async (err) => {
            if (err) throw err;

            const track = Quagga.CameraAccess.getActiveTrack();
            if (track && typeof track.getCapabilities === 'function') {
                const capabilities = track.getCapabilities();
                // Use a higher resolution
                if (capabilities.width.max >= 1280 && capabilities.height.max >= 720) {
                    await track.applyConstraints({advanced: [{width: 1280, height: 720}]});
                }
            }

            const quaggaVideo = /** @type {HTMLVideoElement} */($('#interactive video')[0]);
            const readISBNButton = /** @type {HTMLButtonElement} */(document.querySelector('.barcodescanner__read-isbn'));

            const ocrScanner = new OCRScanner();
            // document.body.append(s.userCanvas);
            ocrScanner.onISBNDetected((isbn) => {
                this.submitISBNThrottled(isbn, '/static/images/openlibrary-logo-tighter.svg');
            });
            ocrScanner.init();

            readISBNButton.addEventListener('click', async () => {
                // Capture image
                const canvas = document.createElement('canvas');
                canvas.width = quaggaVideo.videoWidth;
                canvas.height = quaggaVideo.videoHeight;
                canvas.getContext('2d').drawImage(quaggaVideo, 0, 0, canvas.width, canvas.height);

                this.cameraFlash(quaggaVideo);

                // Ensure init-ing done
                readISBNButton.disabled = true;
                await ocrScanner.init();
                await ocrScanner.doOCR(canvas);
                readISBNButton.disabled = false;
            });
            Quagga.start();

            if (quaggaVideo.paused) {
                quaggaVideo.setAttribute('controls', 'true');
                quaggaVideo.addEventListener('play', () => quaggaVideo.removeAttribute('controls'));
            }
        });

        Quagga.onProcessed(this.handleQuaggaProcessed.bind(this));
        Quagga.onDetected(this.handleQuaggaDetected.bind(this));
    }

    /**
     * @param {HTMLElement} el
     */
    async cameraFlash(el) {
        el.style.animation = 'camera-flash 0.2s';
        await Promise.race([
            new Promise((res) => setTimeout(res, 2000)),
            new Promise((res) => el.addEventListener('animationend', res, {once: true})),
        ]);
        el.style.animation = '';
    }

    handleQuaggaProcessed(result) {
        if (!result) return;

        const drawingCtx = Quagga.canvas.ctx.overlay;

        if (result.boxes) {
            this.clearOverlays();

            result.boxes.forEach(box => {
                if (box !== result.box) {
                    Quagga.ImageDebug.drawPath(box, {x: 0, y: 1}, drawingCtx, BOX_STYLE);
                }
            });
        }

        if (result.box) {
            Quagga.ImageDebug.drawPath(result.box, {x: 0, y: 1}, drawingCtx, RESULT_BOX_STYLE);
            this.clearLater();
        }

        if (result.codeResult && result.codeResult.code && isBarcodeISBN(result.codeResult.code)) {
            Quagga.ImageDebug.drawPath(result.line, {x: 'x', y: 'y'}, drawingCtx, RESULT_LINE_STYLE);
            this.clearLater();
        }
    }

    clearLater() {
        if (this.clearTimeout) clearTimeout(this.clearTimeout);
        this.clearTimeout = setTimeout(this.clearOverlays, 500);
    }

    clearOverlays() {
        if (this.clearTimeout) clearTimeout(this.clearTimeout);
        const drawingCtx = Quagga.canvas.ctx.overlay;
        const drawingCanvas = Quagga.canvas.dom.overlay;
        const canvasWidth = parseFloat(drawingCanvas.getAttribute('width'));
        const canvasHeight = parseFloat(drawingCanvas.getAttribute('height'));
        drawingCtx.clearRect(0, 0, canvasWidth, canvasHeight);
    }

    handleQuaggaDetected(result) {
        const code = result.codeResult.code;
        if (!isBarcodeISBN(code)) return;

        this.submitISBNThrottled(code, Quagga.canvas.dom.image.toDataURL());
    }

    /**
     * @param {string} isbn
     * @param {string} tentativeCoverUrl
     */
    submitISBN(isbn, tentativeCoverUrl) {
        if (isbn === this.lastISBN) return;

        this.lastISBN = isbn;
        const card = LazyBookCard.fromISBN(isbn);
        card.updateState({coverSrc: tentativeCoverUrl});
        $('.barcodescanner__result-strip').prepend(card.render());

        if (this.returnTo) {
            location = this.returnTo.replace('$$$', isbn);
        }
    }
}

export function init() {
    new OLBarcodeScanner().start();
}

/**
 * Check if scanned code is an isbn
 * @param {string} code
 * @return {Boolean}
 */
function isBarcodeISBN(code) {
    return code.startsWith('97');
}


/**
 * @template {(...args: any) => void} TFunc
 */
class ThrottleGrouping {
    /**
     * @param {object} param0
     * @param {TFunc} param0.func
     * @param {function(Parameters<TFunc>[]): Parameters<TFunc>} param0.reducer
     * @param {number} param0.wait
     */
    constructor({func, reducer, wait=100}) {
        this.func = func;
        this.reducer = reducer;
        this.wait = wait;
        /** @type {Parameters<TFunc>[]} */
        this.curGroup = [];
        this.timeout = null;
    }

    submitGroup() {
        this.timeout = null;
        this.func(...this.reducer(this.curGroup));
        this.curGroup = [];
    }

    /**
     * @param  {Parameters<TFunc>} args
     */
    takeNext(...args) {
        this.curGroup.push(args);
        if (!this.timeout) {
            this.timeout = setTimeout(this.submitGroup.bind(this), this.wait);
        }
    }

    asFunction() {
        return this.takeNext.bind(this);
    }
}
