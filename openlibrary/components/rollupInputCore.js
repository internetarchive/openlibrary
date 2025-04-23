import { defineCustomElement as VueDefineCustomElement, h, createApp, getCurrentInstance } from 'vue';
import { createWebComponent } from 'vue-web-component-wrapper';
import AsyncComputed from 'vue-async-computed';
import { kebabCase } from 'lodash';
import PrimeVue from 'primevue/config';
import Aura from '@primeuix/themes/aura';

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
                } else if (elementName = 'ol-author-map') {
                    GivenVue.use(PrimeVue, {
                        theme: {
                            preset: Aura,
                            darkModeSelector: '.ol-author-map-dark',
                        }
                    });
                }
            },
        }
    });
};
