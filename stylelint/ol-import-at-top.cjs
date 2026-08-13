/*
 * stylelint rule `ol/import-at-top`
 *
 * Per the CSS spec, `@import` (and `@charset` / blockless `@layer`) must
 * precede all other statements in a stylesheet. Our Vite build silently drops
 * mid-file `@import`s (webpack's css-loader hoisted them), so this rule
 * catches them at lint time instead of losing styles at build time.
 *
 * See docs/ai/css-vite-migration.md for background.
 *
 * This is CommonJS (not ESM) deliberately: the pre-commit stylelint hook runs
 * in an isolated node env with no repo `node_modules` (pre-commit.ci sandbox)
 * and resolves `stylelint` via NODE_PATH. `require()` honors NODE_PATH while
 * ESM `import` does not, so an ESM plugin cannot find `stylelint` there.
 * `createPlugin` / `utils.report` are stable across the pinned versions
 * (stylelint@16.22.0 in .pre-commit-config.yaml and the repo's ^16.x).
 */
const stylelint = require('stylelint');

const ruleName = 'ol/import-at-top';

const messages = stylelint.utils.ruleMessages(ruleName, {
    rejected:
        'Unexpected @import after the first statement. @import must precede all other rules; Vite silently drops mid-file imports.',
});

const meta = {
    url: 'https://developer.mozilla.org/en-US/docs/Web/CSS/@import',
};

const ruleFunction = (enabled) => {
    return (root, result) => {
        const validOptions = stylelint.utils.validateOptions(result, ruleName, {
            actual: enabled,
            possible: [true, false],
        });
        if (!validOptions || !enabled) return;

        const report = (atRule) => {
            stylelint.utils.report({
                message: messages.rejected,
                node: atRule,
                result,
                ruleName,
            });
        };

        let seenStatement = false;
        root.each((node) => {
            if (node.type === 'comment') return;
            if (node.type === 'atrule' && node.name === 'import') {
                if (seenStatement) report(node);
                return;
            }
            // @charset and blockless @layer statements may legally precede @import
            if (node.type === 'atrule' && node.name === 'charset') return;
            if (node.type === 'atrule' && node.name === 'layer' && !node.nodes) return;
            seenStatement = true;
        });

        // @import nested inside a rule or another at-rule is never valid
        root.walkAtRules('import', (atRule) => {
            if (atRule.parent !== root) report(atRule);
        });
    };
};

ruleFunction.ruleName = ruleName;
ruleFunction.messages = messages;
ruleFunction.meta = meta;

module.exports = stylelint.createPlugin(ruleName, ruleFunction);
