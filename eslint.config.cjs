const js = require("@eslint/js");
const vuePlugin = require("eslint-plugin-vue");
const noJqueryPlugin = require("eslint-plugin-no-jquery");
const globals = require("globals");
const babelParser = require("@babel/eslint-parser");

/** @type {import('eslint').Linter.Config[]} */
module.exports = [
  // Ignore patterns from .eslintignore
  {
    ignores: [
      ".*",
      "conf/",
      "config/",
      "docker/",
      "infogami/",
      "node_modules/",
      "scripts/",
      "static/build/",
      "build/",
      "coverage/",
      "provisioning/",
      "vendor/",
      "tests/screenshots/",
      "venv/",
      "eslint.config.cjs",
    ],
  },

  // Base recommended config
  js.configs.recommended,

  // Vue plugin configuration
  ...vuePlugin.configs["flat/recommended"],

  // No jQuery plugin configuration (disabled variable-pattern check to maintain compatibility)
  {
    plugins: {
      "no-jquery": noJqueryPlugin,
    },
    rules: {
      "no-jquery/variable-pattern": "off",
    },
  },

  // Base configuration for all JS/Vue files (except config and build files)
  {
    files: ["**/*.js", "**/*.vue"],
    ignores: [
      "eslint.config.cjs",
      "*.config.js",
      "*.config.mjs",
      "coverage/**",
      "build/**",
    ],
    languageOptions: {
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
      globals: {
        ...globals.browser,
        ...globals.jquery,
      },
    },
    rules: {
      "prefer-template": "error",
      eqeqeq: ["error", "always"],
      quotes: ["error", "single"],
      "eol-last": ["error", "always"],
      indent: 2,
      "no-console": "error",
      "no-extra-semi": "off",
      "no-extra-boolean-cast": "off",
      "no-mixed-spaces-and-tabs": "error",
      "no-redeclare": "error",
      "no-trailing-spaces": "error",
      "no-undef": "error",
      "no-unused-vars": [
        "error",
        {
          caughtErrors: "none",
        },
      ],
      "no-useless-escape": "error",
      "no-prototype-builtins": "off",
      "no-empty": "off",
      "space-in-parens": "error",
      "vars-on-top": "error",
      "prefer-const": "error",
      "template-curly-spacing": "error",
      "quote-props": ["error", "as-needed"],
      "keyword-spacing": ["error", { before: true, after: true }],
      "key-spacing": ["error", { mode: "strict" }],
      "vue/no-mutating-props": "off",
      "vue/multi-word-component-names": [
        "error",
        {
          ignores: ["Bookshelf", "Shelf"],
        },
      ],
    },
  },

  // Vue-specific configuration
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vuePlugin.parser,
      parserOptions: {
        parser: babelParser,
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
    },
  },

  // JavaScript-specific configuration
  {
    files: ["**/*.js"],
    ignores: [
      "eslint.config.cjs",
      "*.config.js",
      "*.config.mjs",
      "coverage/**",
      "build/**",
    ],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
    },
  },

  // Configuration for build and config files (CommonJS)
  {
    files: [
      "webpack.config.js",
      "webpack.config.css.js",
      "vue.config.js",
      "openlibrary/components/dev/serve-component.js",
      "conf/svgo.config.js",
      "stories/.storybook/main.js",
    ],
    languageOptions: {
      parserOptions: {
        sourceType: "commonjs",
        ecmaVersion: "latest",
      },
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Configuration for Vite config files (ES modules)
  {
    files: [
      "openlibrary/components/vite.config.mjs",
      "openlibrary/components/vite-lit.config.mjs",
    ],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Configuration for Storybook preview files (ES modules)
  {
    files: ["stories/.storybook/preview.js"],
    languageOptions: {
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest",
      },
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Configuration for test files
  {
    files: ["tests/unit/**/*.{js,vue}", "tests/unit/js/setup.js"],
    languageOptions: {
      globals: {
        ...globals.es2021,
        ...globals.jest,
        ...globals.node,
      },
    },
  },
];
