/* eslint-env node */

const {extendDefaultPlugins} = require('svgo'); // eslint-disable-line no-undef
module.exports = {
    plugins: extendDefaultPlugins([
        // Disable plugins enabled by default
        {name: 'removeXMLProcInst', active: false},
        {name: 'collapseGroups', active: false},
        {name: 'mergePaths', active: false},
        {name: 'cleanupIDs', active: false},
        {name: 'convertPathData', active: false},
        {name: 'removeDesc', active: false},
        {name: 'removeTitle', active: false},
        {name: 'removeViewBox', active: false}
    ])
}
