const webpackConfig = require( '../webpack.config' );

module.exports = {
  webpackFinal: async (config) => {
    config.module.rules = config.module.rules.concat(
      webpackConfig.module.rules
    );
    return config;
  },
  "framework": {
    "name": '@storybook/html-webpack5'
  },
  "stories": [
    "../stories/**/*.mdx",
    "../stories/**/*.stories.@(js|jsx|ts|tsx)"
  ],
  "core": {
    // Opt out of telemetry: https://storybook.js.org/docs/html/configure/telemetry
    "disableTelemetry": true
  },
  "addons": [
    "@storybook/addon-essentials"
  ],
}