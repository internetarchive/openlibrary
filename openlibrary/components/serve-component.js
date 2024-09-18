/* eslint-env node */
const fs = require('fs');

const componentName = process.env.npm_config_component || 'HelloWorld';

// Create a copy of openlibrary/components/dev.js to _dev.js
// Replace "HelloWorld" in openlibrary/components/_dev.js with the value of componentName
fs.readFile('openlibrary/components/dev.js', 'utf8', (err, data) => {
    if (err) {
        throw err;
    }
    const result = data.replace(/HelloWorld/g, componentName);
    fs.writeFile('openlibrary/components/_dev.js', result, 'utf8', (err) => {
        if (err) {
            throw err;
        }
    });
});
