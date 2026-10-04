module.exports = {
    plugins: [
        {
            name: 'preset-default',
            params: {
                overrides: {
                    removeXMLProcInst: false,
                    collapseGroups: false,
                    mergePaths: false,
                    cleanupIDs: false,
                    convertPathData: false,
                    removeDesc: false,
                    removeTitle: false,
                    removeViewBox: false,
                },
            },
        },
    ],
};
