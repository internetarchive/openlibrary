// @ts-check
import countBy from 'lodash/countBy';
import maxBy from 'lodash/maxBy';
import Quagga from 'quagga';  // barcode scanning library
import LazyBookCard from './LazyBookCard';

const BOX_STYLE = {color: 'green', lineWidth: 2};
const RESULT_BOX_STYLE = {color: 'blue', lineWidth: 2};
const RESULT_LINE_STYLE = {color: 'red', lineWidth: 15};

class OLBarcodeScanner {
    constructor() {
        this.lastISBN = null;

        const urlParams = new URLSearchParams(location.search)
        this.returnTo = urlParams.get('returnTo');

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
            inputStream: {
                name: 'Live',
                type: 'LiveStream',
                target: $('#interactive')[0],
            },
            decoder: {
                readers: ['ean_reader']
            },
        }, function(err) {
            if (err) throw err;
            Quagga.start();
        });

        Quagga.onProcessed(this.handleQuaggaProcessed.bind(this));
        Quagga.onDetected(this.handleQuaggaDetected.bind(this));
    }

    handleQuaggaProcessed(result) {
        if (!result) return;

        const drawingCtx = Quagga.canvas.ctx.overlay;
        const drawingCanvas = Quagga.canvas.dom.overlay;

        if (result.boxes) {
            const canvasWidth = parseFloat(drawingCanvas.getAttribute('width'));
            const canvasHeight = parseFloat(drawingCanvas.getAttribute('height'));
            drawingCtx.clearRect(0, 0, canvasWidth, canvasHeight);

            result.boxes.forEach(box => {
                if (box !== result.box) {
                    Quagga.ImageDebug.drawPath(box, {x: 0, y: 1}, drawingCtx, BOX_STYLE);
                }
            });
        }

        if (result.box) {
            Quagga.ImageDebug.drawPath(result.box, {x: 0, y: 1}, drawingCtx, RESULT_BOX_STYLE);
        }

        if (result.codeResult && result.codeResult.code && isBarcodeISBN(result.codeResult.code)) {
            Quagga.ImageDebug.drawPath(result.line, {x: 'x', y: 'y'}, drawingCtx, RESULT_LINE_STYLE);
        }
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
        $('#result-strip').prepend(card.render());

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
