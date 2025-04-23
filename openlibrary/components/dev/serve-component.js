/* eslint-env node */
/*
Creates the js files to be imported for the dev server
*/
const fs = require('fs');

const componentName = process.env.COMPONENT || 'HelloWorld';

const data = `
import { createApp } from 'vue'
import HelloWorld from '../HelloWorld.vue'
import PrimeVue from 'primevue/config';
import Aura from '@primeuix/themes/aura';

const app = createApp(HelloWorld);
app.use(PrimeVue, {
    theme: {
        preset: Aura,
        options: {
            darkModeSelector: '.ol-author-map-dark',
        },
    }
});
app.mount('#app')
`

const result = data.replace(/HelloWorld/g, componentName);
fs.writeFileSync('openlibrary/components/dev/_dev.js', result);
