import { defineCustomElement } from 'vue';
import AsyncComputed from 'vue-async-computed';

export const createWebComponentSimple = (rootComponent, name) => {
    // This is the name we use in the DOM like: <ol-barcode-scanner></ol-barcode-scanner>
    const kebabName = name
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
        .toLowerCase();
    const elementName = `ol-${kebabName}`;

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
