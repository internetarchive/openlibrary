/* eslint-env node, es6 */
// https://webpack.js.org/configuration
const
    webpack = require('webpack'),
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
        'all': './openlibrary/plugins/openlibrary/js/index.js'
    },

    resolve: {
        alias: {}
    },
    plugins: [
        new webpack.ProvidePlugin({
            $: 'jquery',
            jQuery: 'jquery'
        })
    ],
    module: {
        rules: [ {
            test: /\.js$/,
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
            loader: [
                'style-loader',
                'css-loader',
                'less-loader' // compiles Less to CSS
            ]
        } ]
    },
    optimization: {
        // Don't produce production output when a build error occurs.
        noEmitOnErrors: prod
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

        // Expose the module.exports of each module entry chunk through the global
        // ol (open library)
        library: [ 'ol' ],
        libraryTarget: 'this'
    },

    // Accurate source maps at the expense of build time.
    // The source map is intentionally exposed
    // to users via sourceMapFilename for prod debugging.
    devtool: 'source-map',

    performance: {
        maxAssetSize: 703 * 1024,
        maxEntrypointSize: 703 * 1024,
        // Size violations for prod builds fail; development builds are unchecked.
        hints: prod ? 'error' : false
    }
};
