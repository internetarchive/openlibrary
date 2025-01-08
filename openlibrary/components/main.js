import { defineCustomElement } from 'vue';
import ele from './BarcodeScanner.vue';

customElements.define('ol-barcode-scanner', defineCustomElement(ele));
