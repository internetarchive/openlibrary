const fs = require('fs').promises;
const path = require('path');

const directoryPath = path.join(__dirname, '.');

const getVueComponentFiles = async () => {
    try {
        const files = await fs.readdir(directoryPath);
        const f = files.filter(file => file.endsWith('.vue'));
        return f;
    } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Unable to scan directory:', err);
        return [];
    }
};

const generateComponentFile = async (componentName) => {
    const template = `
import { createWebComponentSimple } from "../rollupInputCore.js"
import rootComponent from '../${componentName}.vue';
createWebComponentSimple(rootComponent, '${componentName}');`;

    const outputDir = path.join(__dirname, 'build');

    try {
        // Create the build directory if it doesn't exist
        await fs.mkdir(outputDir, { recursive: true });

        const filePath = path.join(outputDir, `${componentName}.js`);
        await fs.writeFile(filePath, template);
        // eslint-disable-next-line no-console
        console.log(`Generated ${filePath}.js`)

    } catch (err) {
        // eslint-disable-next-line no-console
        console.error(`Error creating file for ${componentName}:`, err);
    }
};

getVueComponentFiles().then(async vueFiles => {
    vueFiles.forEach(file=>generateComponentFile(file.replace('.vue', '')))
});
