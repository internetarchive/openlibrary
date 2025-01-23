/* eslint-env node */
/*
Creates the js files to be imported for the dev server
*/
const fs = require('fs');

const componentName = process.env.COMPONENT || 'HelloWorld';

const data = `
import { createApp } from 'vue'
import HelloWorld from '../HelloWorld.vue'

createApp(HelloWorld).mount('#app')
`

const result = data.replace(/HelloWorld/g, componentName);
fs.writeFileSync('openlibrary/components/dev/_dev.js', result);
