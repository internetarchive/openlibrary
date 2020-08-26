/* eslint-env node, es6 */
module.exports = {
    plugins: [
        require('autoprefixer'),
        require('cssnano')({
            preset: 'default',
        }),
    ]
};
