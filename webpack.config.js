/* eslint-env node, es6 */
// https://webpack.js.org/configuration
const
    webpack = require('webpack'),
    path = require('path'),
    prod = process.env.NODE_ENV === 'production',
    // The output directory for all build artifacts. Only absolute paths are accepted by
    // output.path.
    distDir = path.resolve(__dirname, process.env.BUILD_DIR || 'static/build/js');

module.exports = {
    // Fail on the first build error instead of tolerating it for prod builds. This seems to
    // correspond to optimization.noEmitOnErrors.
    bail: prod,

    // Specify that all paths are relative the Webpack configuration directory not the current
    // working directory.
    context: __dirname,

    // A map of ResourceLoader module / entry chunk names to JavaScript files to pack.
    entry: {
        all: './openlibrary/plugins/openlibrary/js/index.js',
        partnerLib: './openlibrary/plugins/openlibrary/js/partner_ol_lib.js',
        sw: './openlibrary/plugins/openlibrary/js/service-worker.js',
    },

    resolve: {
        alias: {}
    },
    plugins: [
        new webpack.ProvidePlugin({
            $: 'jquery',
            jQuery: 'jquery'
        }),
    ],
    module: {
        rules: [{
            test: /\.js$/,
            exclude: /node_modules/,
            use: {
                loader: 'babel-loader',
                options: {
                    // Beware of https://github.com/babel/babel-loader/issues/690.
                    // Changes to browsers require manual invalidation.
                    cacheDirectory: true
                }
            }
        }, {
            test: /\.css$/,
            use: [
                {
                    loader: 'style-loader'
                },
                {
                    loader: 'css-loader',
                    options: {
                        url: false
                    }
                }
            ]
        }]
    },
    optimization: {
        splitChunks: {
            cacheGroups: {
                // Turn off webpack's default 'vendors' cache group. If this is desired
                // later on, we can explicitly turn this on for clarity.
                // https://webpack.js.org/plugins/split-chunks-plugin/#optimization-splitchunks
                vendors: false,

            }
        },
        // Don't produce production output when a build error occurs.
        emitOnErrors: !prod
    },

    output: {
        // Specify the destination of all build products.
        path: distDir,
        // base path for build products when referenced from production
        // (see https://webpack.js.org/guides/public-path/)
        publicPath: '/static/build/js/',

        // Store outputs per module in files named after the modules. For the JavaScript entry
        // itself, append .js to each ResourceLoader module entry name.
        filename: '[name].js',

        // This option determines the name of **non-entry** chunk files.
        chunkFilename: '[name].[contenthash].js',
    },

    // Accurate source maps at the expense of build time.
    // The source map is intentionally exposed
    // to users via sourceMapFilename for prod debugging.
    devtool: 'source-map',
    mode: prod ? 'production' : 'development',

    performance: {
        maxAssetSize: 703 * 1024,
        maxEntrypointSize: 703 * 1024,
        // Size violations for prod builds fail; development builds are unchecked.
        hints: prod ? 'error' : false
    },

    // Useful for developing in docker/windows, which doesn't support file watchers
    watchOptions: process.env.FORCE_POLLING === 'true' ? {
        poll: 1000, // Check for changes every second
        aggregateTimeout: 300, // Delay before rebuilding
        ignored: /node_modules/
    } : undefined,
};
