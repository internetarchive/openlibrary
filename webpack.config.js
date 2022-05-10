/* eslint-env node, es6 */
// https://webpack.js.org/configuration
const
    webpack = require('webpack5'),
    path = require('path'),
    prod = process.env.NODE_ENV === 'production',
    // The output directory for all build artifacts. Only absolute paths are accepted by
    // output.path.
    distDir = path.resolve(__dirname, 'static/build');

module.exports = {
    // Apply the rule of silence: https://wikipedia.org/wiki/Unix_philosophy.
    stats: {
        all: false,
        // Output a timestamp when a build completes. Useful when watching files.
        builtAt: true,
        errors: true,
        warnings: true
    },

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
        vue: './openlibrary/plugins/openlibrary/js/vue.js',
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
            test: /\.less$/,
            use: [
                {
                    loader: 'style-loader'
                },
                {
                    loader: 'css-loader',
                    options: {
                        url: false
                    }
                },
                {
                    // compiles Less to CSS
                    loader: 'less-loader'
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
        publicPath: '/static/build/',

        // Store outputs per module in files named after the modules. For the JavaScript entry
        // itself, append .js to each ResourceLoader module entry name.
        filename: '[name].js',

        // This option determines the name of **non-entry** chunk files.
        chunkFilename: '[name].[contenthash].js',

        // Expose the module.exports of each module entry chunk through the global
        // ol (open library)
        library: ['ol'],
        libraryTarget: 'this'
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
    }
};
