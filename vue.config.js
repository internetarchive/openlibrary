/* eslint-env node, es6 */
module.exports = {
    lintOnSave: false,
    publicPath: '/static/components/',

    // Add support for running from gitpod
    ...(process.env.GITPOD_WORKSPACE_ID ? {
        devServer: {
            allowedHosts: [
                // It'll pick the first free one, so will be 8080 if OL not running, otherwise 8081.
                // The rest are just in case/if you run multiple
                `8080-${process.env.GITPOD_WORKSPACE_ID}.${process.env.GITPOD_WORKSPACE_CLUSTER_HOST}`,
                `8081-${process.env.GITPOD_WORKSPACE_ID}.${process.env.GITPOD_WORKSPACE_CLUSTER_HOST}`,
                `8082-${process.env.GITPOD_WORKSPACE_ID}.${process.env.GITPOD_WORKSPACE_CLUSTER_HOST}`,
                `8083-${process.env.GITPOD_WORKSPACE_ID}.${process.env.GITPOD_WORKSPACE_CLUSTER_HOST}`,
            ],
            client: {
                webSocketURL: {
                    port: 443,
                },
            },
        },
    } : {}),
};
