import { parseSync, traverse } from '@babel/core';
import { readFileSync } from 'fs';
import path from 'path';

// new_pr_labeler.mjs cannot be imported here: it runs main() at module load and
// depends on @octokit/action, which the workflow installs ad hoc. It also runs
// only from the default branch, so a PR changing it cannot exercise it. So this
// checks the source itself: every `const {a, b} = helper()` in the script must
// name keys that helper actually returns. A key renamed on one side of that
// boundary left the lead undefined on every PR for four weeks (#13743).
const scriptPath = path.join(__dirname, '../../../scripts/gh_scripts/new_pr_labeler.mjs');

function keyName(node) {
    return node.key.type === 'Identifier' ? node.key.name : node.key.value;
}

function destructuringPairs(source) {
    const ast = parseSync(source, {
        sourceType: 'module',
        configFile: false,
        babelrc: false,
    });

    const returnedKeys = new Map();
    traverse(ast, {
        FunctionDeclaration(fnPath) {
            const keys = new Set();
            fnPath.traverse({
                Function(inner) {
                    inner.skip();
                },
                ReturnStatement(retPath) {
                    const arg = retPath.node.argument;
                    if (arg?.type !== 'ObjectExpression') {
                        return;
                    }
                    for (const prop of arg.properties) {
                        if (prop.type === 'ObjectProperty' && !prop.computed) {
                            keys.add(keyName(prop));
                        }
                    }
                },
            });
            returnedKeys.set(fnPath.node.id.name, keys);
        },
    });

    const pairs = [];
    traverse(ast, {
        VariableDeclarator({ node }) {
            let call = node.init;
            if (call?.type === 'AwaitExpression') {
                call = call.argument;
            }
            if (node.id.type !== 'ObjectPattern' || call?.type !== 'CallExpression') {
                return;
            }
            const callee = call.callee.name;
            if (!returnedKeys.has(callee)) {
                return;
            }
            const destructured = node.id.properties
                .filter((prop) => prop.type === 'ObjectProperty')
                .map(keyName);
            pairs.push({ callee, destructured, returned: [...returnedKeys.get(callee)] });
        },
    });
    return pairs;
}

describe('new_pr_labeler.mjs', () => {
    const pairs = destructuringPairs(readFileSync(scriptPath, 'utf8'));

    test('finds both helpers the script destructures', () => {
        // Guards against the walker matching nothing and every check below
        // passing vacuously.
        expect(pairs.map((pair) => pair.callee).sort()).toEqual(['getLinkedIssueMetadata', 'parseArgs']);
    });

    test.each(pairs)('every key destructured from $callee() is one it returns', ({ destructured, returned }) => {
        for (const key of destructured) {
            expect(returned).toContain(key);
        }
    });
});
