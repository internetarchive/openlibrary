import { defineCustomElement as VueDefineCustomElement, h, createApp, getCurrentInstance } from 'vue';
import { createWebComponent } from 'vue-web-component-wrapper';
import AsyncComputed from 'vue-async-computed';
import { kebabCase } from 'lodash';


export const createWebComponentSimple = (rootComponent, name) => {
    // This is the name we use in the DOM like: <ol-barcode-scanner></ol-barcode-scanner>
    const elementName = `ol-${kebabCase(name)}`;

    createWebComponent({
        rootComponent,
        elementName,
        VueDefineCustomElement,
        h,
        createApp,
        getCurrentInstance,
        plugins: {
            install(GivenVue) {
                if (elementName === 'ol-merge-ui') {
                    GivenVue.use(AsyncComputed);
                }
            },
        }
    });
};
