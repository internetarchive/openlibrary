<template>
  <div id="page-barcodescanner">
    <OLBarcodeScanner :state="state" :lastISBN="lastISBN" v-on:update:lastISBN="updateLastISBN" v-on:update:state="updateState"/>
    <div class="barcodescanner__toolbar">
      <details class="barcodescanner__advanced">
        <summary class="glass-button icon-button">
          <svg xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:cc="http://creativecommons.org/ns#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:svg="http://www.w3.org/2000/svg" xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 4.2742091 4.2333331" height="16" width="16"><path d="M 1.6561242,0.00198689 C 1.5224783,0.02929715 1.3981294,0.07810697 1.2746523,0.12924106 1.2650645,0.49211882 1.3252052,0.96714289 1.1837149,1.0917824 1.0448392,1.2143878 0.58027458,1.1118292 0.22117379,1.0734786 0.14476319,1.2109015 0.08433198,1.3552972 0.03958966,1.5092805 0.31734074,1.739384 0.70229912,1.9967977 0.71159623,2.1812871 0.72089334,2.3678103 0.34755635,2.6490479 0.09421016,2.9076237 0.15435082,3.0575395 0.23947746,3.1943815 0.33041481,3.3254125 0.68399544,3.2519072 1.1244458,3.1083831 1.2746523,3.2164619 1.427764,3.3265746 1.4286355,3.8007271 1.47454,4.1606995 1.6195168,4.2042803 1.772338,4.2214213 1.9283551,4.2333334 2.0919261,3.9111305 2.2581119,3.466322 2.4367907,3.4160595 2.6201181,3.3646352 2.996651,3.6821892 3.3083946,3.8701651 3.4353582,3.7821329 3.5483762,3.6743446 3.6535496,3.5613266 3.5059581,3.2286644 3.2345987,2.8105852 3.3083946,2.6351022 c 0.073796,-0.1754829 0.566833,-0.272812 0.9079206,-0.3994851 0.00261,-0.042709 0.018304,-0.083674 0.018304,-0.1272542 0,-0.1112747 -0.020046,-0.2202252 -0.036317,-0.3268514 C 3.8461741,1.6879593 3.3458736,1.6411833 3.2540645,1.4726731 3.1631272,1.3053253 3.3946833,0.85586816 3.5082825,0.51013195 3.3914875,0.4064111 3.2645238,0.31431163 3.1268104,0.23761048 2.8356947,0.45551144 2.4966408,0.81548385 2.3095366,0.78236289 2.1253376,0.74982302 1.9242876,0.30617665 1.7284674,0.00140584 c -0.023243,0.0040672 -0.049682,-0.0046482 -0.072634,0 z M 2.0192925,1.0914918 c 0.5415565,0 0.9805543,0.4389978 0.9805543,0.9805543 0,0.5415566 -0.4389978,0.9805543 -0.9805543,0.9805543 -0.5415566,0 -0.9805543,-0.4389977 -0.9805543,-0.9805543 0,-0.5415565 0.4389977,-0.9805543 0.9805543,-0.9805543 z" style="fill:currentColor;stroke:none;"></path></svg>
                Advanced
        </summary>
        <div class="barcodescanner__controls">
          <button class="barcodescanner__read-isbn glass-button">
            Read Text ISBN
            <br>
            <small>For books that print the ISBN without a barcode</small>
          </button>
        </div>
      </details>
      <div class="barcodescanner__result-strip">
        <LazyBookCard v-if="lastISBN" :isbn="lastISBN" :state="state"/>
        <div class="empty">
          Point your camera at a barcode! 📷
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import OLBarcodeScanner from './BarcodeScanner/components/OLBarcodeScanner.vue';
import LazyBookCard from './BarcodeScanner/components/LazyBookCard.vue';
import Promise from 'promise-polyfill';
import CONFIGS from './configs';

export default {
    components: { OLBarcodeScanner, LazyBookCard },
    data() {
        return {
            lastISBN: null,
            state: {},
        }
    },
    methods: {
        updateLastISBN(variable) {
            this.lastISBN = variable;
            this.fromISBN(variable);
        },

        updateState(newState) {
            const oldState = this.state;
            newState = Object.assign({}, oldState, newState);
            this.state = newState;
        },

        fromISBN(isbn) {
            fetch(`https://${CONFIGS.OL_BASE_PUBLIC}/isbn/${isbn}.json`).then(r => r.json())
                .then(editionRecord => {
                    this.updateState({
                        title: editionRecord.title,
                        identifier: isbn,
                        link: editionRecord.key,
                    });

                    if (editionRecord.covers) {
                        const coverId = editionRecord.covers.find(x => x !== -1);
                        if (coverId) {
                            this.updateState({
                                coverSrc: `https://covers.openlibrary.org/b/id/${coverId}-M.jpg`,
                            });
                        }
                    }

                    return fetch(`https://${CONFIGS.OL_BASE_PUBLIC}${editionRecord.works[0].key}.json`).then(r => r.json())
                }).then(workRecord => {
                    return Promise.all(
                        workRecord.authors
                            .map(a => fetch(`https://${CONFIGS.OL_BASE_PUBLIC}${a.author.key}.json`).then(r => r.json()))
                    );
                }).then(authorRecords => {
                    this.updateState({
                        loading: false,
                        byline: authorRecords.map(a => a.name).join(', '),
                    });
                })
                // eslint-disable-next-line no-unused-vars
                .catch((err) => {
                    this.updateState({loading: false, errored: true});
                }
                );
        }
    }
}
</script>

<style lang="less">
  @keyframes pulse {
    0% { filter: brightness(1.3); }
    100% { filter: brightness(1.2); }
  }
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

  #interactive.viewport {
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
  a.lazy-book-card {
    background: hsl(0, 0%, 100%);
    flex-shrink: 0;
    margin-right: 6px;
    width: 80vw;
    max-width: 300px;
    height: 120px;
    border: 1px solid hsl(0, 0%, 67%);
    border-radius: 4px;
    display: flex;
    overflow: hidden;
    color: hsl(0, 0%, 0%);
    text-decoration: none;
    position: relative;
    transition-property: background-color border-color;
    transition-duration: .2s;

    &:first-child { animation: slideUp .8s; }
    &:nth-child(2) { animation: shiftRight .8s; }
    &:hover {
      background: lighten(hsl(240, 100%, 50%), 45%);
      border-color: lighten(hsl(240, 100%, 50%), 15%);
      color: lighten(hsl(240, 100%, 50%), 10%);
    }
    &::before {
      display: none;
      content: "";
      position: absolute;
      width: 6px;
      height: 6px;
      border-radius: 100px;
      margin: 10px;
      right: 0;
    }
    &.loading::before {
      display: block;
      background: hsl(240, 100%, 50%);
      opacity: 0;
      animation: pulse .5s infinite alternate;
      // Only show loading animation if it takes
      // longer than this
      animation-delay: .5s;
    }
    &.errored::before {
      display: block;
      background: hsl(8, 78%, 49%);
    }
    .title { font-weight: bold; line-height: 1.1em; }
    .byline { font-size: .9em; margin-top: .1em; }
    .cover {
      width: 25%;
      img { width: 100%; height: 100%; object-fit: cover; }
    }
    .identifier {
      margin-top: 4px;
      padding-top: 4px;
      color: hsl(0, 0%, 33%);
      border-top: 1px dotted;
      font-family: monospace;
      font-size: 1.2em;
    }
    .info {
      flex: 1;
      padding: 8px;
    }
  }
</style>
