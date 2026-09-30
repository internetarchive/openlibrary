/*
Creates the js files to be imported for the dev server
*/
const fs = require('fs');

const componentName = process.env.COMPONENT || 'HelloWorld';

// Components reference design tokens (var(--z-index-fixed), etc). Real pages get
// them from site/head.html; without the import here every var() lookup fails and
// the whole declaration is dropped, so layering silently differs from the site.
const data = `
import { createApp } from 'vue'
import '../../../static/css/tokens.css'
import HelloWorld from '../HelloWorld.vue'

createApp(HelloWorld).mount('#app')
`;

const result = data.replace(/HelloWorld/g, componentName);
fs.writeFileSync('openlibrary/components/dev/_dev.js', result);
