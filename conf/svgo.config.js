module.exports = {
    plugins: [
        {
            name: 'preset-default',
            params: {
                overrides: {
                    removeXMLProcInst: false,
                    collapseGroups: false,
                    mergePaths: false,
                    cleanupIds: false,
                    convertPathData: false,
                    removeDesc: false
                }
            }
        }
    ]
};
