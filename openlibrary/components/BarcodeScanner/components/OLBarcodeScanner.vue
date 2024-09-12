<template>
  <div id="interactive" class="viewport"></div>
</template>

<script>
import Quagga from '@ericblade/quagga2';
import maxBy from 'lodash/maxBy';
import countBy from 'lodash/countBy';
import { OCRScanner, ThrottleGrouping } from '../utils/classes';
export default {
    props: {
        lastISBN: {
            type: String || null,
        },
        state: {
            type: Object || null,
        },
    },
    data() {
        return {
            returnTo: new URLSearchParams(location.search).get('returnTo'),
            BOX_STYLE: {color: 'green', lineWidth: 2},
            RESULT_BOX_STYLE: {color: 'blue', lineWidth: 2},
            RESULT_LINE_STYLE: {color: 'red', lineWidth: 15},
            submitISBNThrottled: new ThrottleGrouping({
                func: this.submitISBN.bind(this),
                // Use the most frequent
                reducer: (groupOfArgs) => {
                    const isbnCounts = Array.from(
                        Object.entries(
                            countBy(groupOfArgs, (arg) => arg[0])
                        )
                    );

                    /* eslint-disable no-unused-vars */
                    const mostFrequentISBN = maxBy(isbnCounts, ([isbn, count]) => count)[0];
                    return groupOfArgs.reverse().find((args) => args[0] === mostFrequentISBN);
                },
                wait: 300,
            }).asFunction(),
            childState: this.state,
            childLastISBN: this.lastISBN,
        }
    },
    methods: {
        start() {
            Quagga.init({
                locator: {
                    halfSample: true,
                },
                inputStream: {
                    name: 'Live',
                    type: 'LiveStream',
                    target: document.getElementById('interactive'),
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

                const quaggaVideo = document.getElementById('interactive').getElementsByTagName('video')[0];
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
        },

        async cameraFlash(el) {
            el.style.animation = 'camera-flash 0.2s';
            await Promise.race([
                new Promise((res) => setTimeout(res, 2000)),
                new Promise((res) => el.addEventListener('animationend', res, {once: true})),
            ]);
            el.style.animation = '';
        },

        handleQuaggaProcessed(result) {
            if (!result) return;

            const drawingCtx = Quagga.canvas.ctx.overlay;

            if (result.boxes) {
                this.clearOverlays();

                result.boxes.forEach(box => {
                    if (box !== result.box) {
                        Quagga.ImageDebug.drawPath(box, {x: 0, y: 1}, drawingCtx, this.BOX_STYLE);
                    }
                });
            }

            if (result.box) {
                Quagga.ImageDebug.drawPath(result.box, {x: 0, y: 1}, drawingCtx, this.RESULT_BOX_STYLE);
                this.clearLater();
            }

            if (result.codeResult && result.codeResult.code && this.isBarcodeISBN(result.codeResult.code)) {
                Quagga.ImageDebug.drawPath(result.line, {x: 'x', y: 'y'}, drawingCtx, this.RESULT_LINE_STYLE);
                this.clearLater();
            }
        },

        clearLater() {
            if (this.clearTimeout) clearTimeout(this.clearTimeout);
            this.clearTimeout = setTimeout(this.clearOverlays, 500);
        },

        clearOverlays() {
            if (this.clearTimeout) clearTimeout(this.clearTimeout);
            const drawingCtx = Quagga.canvas.ctx.overlay;
            const drawingCanvas = Quagga.canvas.dom.overlay;
            const canvasWidth = parseFloat(drawingCanvas.getAttribute('width'));
            const canvasHeight = parseFloat(drawingCanvas.getAttribute('height'));
            drawingCtx.clearRect(0, 0, canvasWidth, canvasHeight);
        },

        handleQuaggaDetected(result) {
            const code = result.codeResult.code;
            if (!this.isBarcodeISBN(code)) return;

            this.submitISBNThrottled(code, Quagga.canvas.dom.image.toDataURL());
        },

        submitISBN(isbn, tentativeCoverUrl) {
            if (isbn === this.lastISBN) return;

            this.childLastISBN = isbn;
            const oldState = this.childState;
            const newState = Object.assign({}, oldState, {coverSrc: tentativeCoverUrl});
            this.childState = newState;

            if (this.returnTo) {
                location = this.returnTo.replace('$$$', isbn);
            }
            this.$emit('update:lastISBN', this.childLastISBN);
            this.$emit('update:state', this.childState);
        },

        isBarcodeISBN(code) {
            return code.startsWith('97');
        }
    },
    mounted() {
        this.start();
    }
}
</script>
