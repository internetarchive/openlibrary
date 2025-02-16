<template>
  <div id="page-barcodescanner">
    <div class="viewport" ref="viewport" :class="{'loading': loading}"></div>
    <div class="barcodescanner__toolbar">
      <details class="barcodescanner__advanced">
        <summary class="glass-button icon-button">
          <SettingsIcon/>
                Advanced
        </summary>
        <div class="barcodescanner__controls">
          <button class="barcodescanner__read-isbn glass-button" @click="handleISBNDetected" :disabled="disableISBNTextButton || canvasInactive">
            Read Text ISBN
            <br>
            <small>For books that print the ISBN without a barcode</small>
          </button>
        </div>
      </details>
      <div class="barcodescanner__result-strip">
         <LazyBookCard v-for="isbnObj in isbnList" :key="isbnObj.isbn" :isbn="isbnObj.isbn" :tentativeCover="isbnObj.cover" />
        <div class="empty">
          Point your camera at a barcode! 📷
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import LazyBookCard from './BarcodeScanner/components/LazyBookCard.vue';
import SettingsIcon from './LibraryExplorer/components/icons/SettingsIcon.vue';
import Quagga from '@ericblade/quagga2';
import maxBy from 'lodash/maxBy';
import countBy from 'lodash/countBy';
import { OCRScanner, ThrottleGrouping } from './BarcodeScanner/utils/classes.js';

export default {
    components: { LazyBookCard, SettingsIcon },
    data() {
        return {
            disableISBNTextButton: false,
            canvasInactive: true,
            lastISBN: null,
            isbnList: [],
            seenISBN: new Set(),
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
            quaggaVideo: null,
            ocrScanner: null,
        }
    },
    methods: {
        start() {
            return new Promise((res, rej) => {
                Quagga.init({
                    locator: {
                        halfSample: true,
                    },
                    inputStream: {
                        name: 'Live',
                        type: 'LiveStream',
                        target: this.$refs.viewport,
                        constraints: {
                            // Vertical - This is *essential* for iPhone/iPad
                            aspectRatio: {ideal: 720/1280},
                        },
                    },
                    decoder: {
                        readers: ['ean_reader']
                    },
                }, async (err) => {
                    if (err) {
                        rej(err);
                        return;
                    }
                    const track = Quagga.CameraAccess.getActiveTrack();
                    if (track && typeof track.getCapabilities === 'function') {
                        const capabilities = track.getCapabilities();
                        // Use a higher resolution
                        if (capabilities.width.max >= 1280 && capabilities.height.max >= 720) {
                            await track.applyConstraints({advanced: [{width: 1280, height: 720}]});
                        }
                    }
                    const quaggaVideo = this.$refs.viewport.getElementsByTagName('video')[0];
                    const ocrScanner = new OCRScanner();
                    // document.body.append(s.userCanvas);
                    ocrScanner.onISBNDetected((isbn) => {
                        this.submitISBNThrottled(isbn, '/static/images/openlibrary-logo-tighter.svg');
                    });
                    ocrScanner.init();

                    this.quaggaVideo = quaggaVideo;
                    this.ocrScanner = ocrScanner;
                    Quagga.start();
                    if (quaggaVideo.paused) {
                        quaggaVideo.setAttribute('controls', 'true');
                        quaggaVideo.addEventListener('play', () => quaggaVideo.removeAttribute('controls'));
                    }
                    res();
                });
                Quagga.onProcessed(this.handleQuaggaProcessed);
                Quagga.onDetected(this.handleQuaggaDetected);
            });
        },

        async handleISBNDetected() {
            const canvas = document.createElement('canvas');
            canvas.width = this.quaggaVideo.videoWidth;
            canvas.height = this.quaggaVideo.videoHeight;
            canvas.getContext('2d').drawImage(this.quaggaVideo, 0, 0, canvas.width, canvas.height);

            this.cameraFlash(this.quaggaVideo);

            this.disableISBNTextButton = true;
            await this.ocrScanner.init();
            await this.ocrScanner.doOCR(canvas);
            this.disableISBNTextButton = false;
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
            if (this.seenISBN.has(isbn)) return;

            if (this.returnTo) {
                location = this.returnTo.replace('$$$', isbn);
            }
            this.isbnList.unshift({isbn: isbn, cover: tentativeCoverUrl});
            this.seenISBN.add(isbn);
        },

        isBarcodeISBN(code) {
            return code.startsWith('97');
        },

    },
    async mounted() {
        await this.start();
        this.canvasInactive = false;
    }
}
</script>

<style lang="less">
  @keyframes camera-flash {
  0% { filter: brightness(1.3); }
  100% { filter: brightness(1.2); }
  }

  @keyframes slideUp {
    0% { transform: translateY(50%); opacity: .5; }
    100% { transform: translateY(0); opacity: 1; }
  }

  @keyframes shiftRight {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(0); }
  }

  #page-barcodescanner {
    display: flex;
    flex-direction: column;
    // stylelint-disable declaration-block-no-duplicate-properties
    // Fallback browsers that don't support dvh
    height: calc(100vh - 60px);
    height: 100dvh; // stylelint-disable-line unit-no-unknown
    // stylelint-enable declaration-block-no-duplicate-properties
  }

  .viewport {
    position: relative;
    flex: 1;
    min-height: 0;
    video, canvas {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    canvas {
      position: absolute;
      top: 0;
      left: 0;
    }

    video[controls] + canvas {
      pointer-events: none;
    }
  }

  .barcodescanner__toolbar {
    font-family: "Lucida Grande", Veranda, Geneva, Helvetica, Arial, sans-serif;
    position: relative;
    background: hsl(0, 0%, 100%);
  }

  .glass-button {
    cursor: pointer;

    border-radius: 10px;
    // stylelint-disable-next-line sh-waqar/declaration-use-variable
    color: rgba(255,255,255, .8);
    background: rgba(0,0,0,.5);
    border: 1px solid rgba(255,255,255, .45);
    font-size: .8em;
    backdrop-filter: blur(8px);

    box-shadow: 0 0 3px 0 rgba(0,0,0,.4);
    &:disabled {
      opacity: .5;
    }
  }

  .icon-button {
    display: flex;
    align-items: center;
    padding-right: 10px;
  }

  details.barcodescanner__advanced {
    position: absolute;
    bottom: 100%;
    right: 0;

    // For slide up effect
    transform: translateY(100%);
    transition: transform .2s;
    > :not(summary) {
      transition: opacity .2s;
      opacity: 0;
    }
    &[open] {
      transform: translateY(0);
    }
    &[open] > :not(summary) {
      opacity: 1;
    }

    & > summary {
      position: absolute;
      bottom: 100%;
      right: 0;
      margin: 5px;

      &::marker {
        content: none;
      }

      &::-webkit-details-marker {
        display: none;
      }

      svg {
        width: 32px;
        height: 32px;
        padding: 6px;
        box-sizing: border-box;

        transition: transform .2s;
      }
    }

    &[open] > summary svg,
    &:not([open]) > summary:hover svg {
      transform: rotate(20deg);
    }

    // stylelint-disable-next-line no-descending-specificity
    &[open] > summary:hover svg {
      transform: rotate(-20deg);
    }
  }

  .barcodescanner__controls {
    display: flex;
    padding: 4px;
    padding-top: 0;
    overflow-x: auto;

    & > button {
      padding: 8px;
      text-align: left;
    }
  }

  .barcodescanner__result-strip {
    display: flex;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 10px;
    .empty {
      display: none;
      &:first-child:last-child { display: flex; }
      width: 80vw;
      max-width: 300px;
      height: 80px;
      border: 1px dashed;
      justify-content: center;
      align-items: center;
      flex-shrink: 0;
      border-radius: 4px;
    }
  }
</style>
