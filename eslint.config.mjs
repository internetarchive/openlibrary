import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";

import noJquery from "eslint-plugin-no-jquery";
import pluginVue from "eslint-plugin-vue";
import pluginJest from "eslint-plugin-jest";

// Shared rules across environments
const commonRules = {
  "prefer-template": "error",
  eqeqeq: ["error", "always"],
  quotes: ["error", "single"],
  "eol-last": ["error", "always"],
  indent: 2,
  "no-console": "error",
  "no-extra-semi": "error",
  "no-mixed-spaces-and-tabs": "error",
  "no-redeclare": "error",
  "no-trailing-spaces": "error",
  "no-undef": "error",
  "no-unused-vars": "error",
  "no-useless-escape": "error",
  "space-in-parens": "error",
  "vars-on-top": "error",
  "prefer-const": "error",
  "template-curly-spacing": "error",
  "quote-props": ["error", "as-needed"],
  "keyword-spacing": ["error", { before: true, after: true }],
  "key-spacing": ["error", { mode: "strict" }],
};

// Shared parser settings
const babelParserOptions = {
  parser: "@babel/eslint-parser",
  babelOptions: {
    configFile: "./.babelrc",
  },
};

export default defineConfig([
  // Ignore certain folders globally
  globalIgnores([
    "**/scripts/solr_restarter/index.js",
    "static/",
    "**/vendor/",
  ]),

  // Vue-specific configuration
  ...pluginVue.configs['flat/recommended'],
  {
    files: ["**/*.vue"],
    languageOptions: {
      globals: {
        ...globals.browser,
      },
      parserOptions: babelParserOptions,
    },
    rules: {
      ...commonRules,
      "vue/no-mutating-props": "off",
      "vue/multi-word-component-names": ["error", { ignores: ["Bookshelf", "Shelf"] }],
    },
  },

  // Browser JavaScript (excluding tests and config files)
  {
    files: ["**/*.js"],
    ignores: [
      "**/webpack.config.js",
      "**/vue.config.js",
      "**/stories/**/*.js",
      "openlibrary/components/dev/serve-component.js",
      "**/tests/**/*.js",
    ],
    plugins: {
      "no-jquery": noJquery,
    },
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.jquery,
      },
      parserOptions: babelParserOptions,
    },
    rules: {
      ...commonRules,
    },
  },

  // Test files
  {
    files: ["**/tests/**/*.js"],
    plugins: {
      jest: pluginJest,
      "no-jquery": noJquery,
    },
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.jquery,
        ...pluginJest.environments.globals.globals,
        global: true,
      },
      parserOptions: babelParserOptions,
    },
    rules: {
      ...commonRules,
      // We should enable this recommended rule eventually but it will require a few changes.
      // ...pluginJest.configs.recommended.rules,
    },
  },
]);
