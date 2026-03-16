import { defineCustomElement } from 'vue';
import AsyncComputed from 'vue-async-computed';
import { kebabCase } from 'lodash';

export const createWebComponentSimple = (rootComponent, name) => {
    // This is the name we use in the DOM like: <ol-barcode-scanner></ol-barcode-scanner>
    const elementName = `ol-${kebabCase(name)}`;

    const WebComponent = defineCustomElement(rootComponent, {
        configureApp(app) {
            if (elementName === 'ol-merge-ui') {
                app.use(AsyncComputed);
            }
        },
    });

    if (!customElements.get(elementName)) {
        customElements.define(elementName, WebComponent);
    }
};
