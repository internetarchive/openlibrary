import { execFileSync } from 'child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'fs';
import os from 'os';
import path from 'path';

// Invoke the real stylelint CLI (repo config + `ol/import-at-top` plugin) on a
// fixture file, and return how many times the rule fired. Spawning the CLI
// avoids importing stylelint into jest (its FileCache module breaks under the
// repo's jsdom test environment).
const repoRoot = path.join(__dirname, '../../..');
const stylelintBin = path.join(repoRoot, 'node_modules/.bin/stylelint');

function lintImportAtTop(code) {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'ol-import-at-top-'));
    const file = path.join(dir, 'test.css');
    writeFileSync(file, code);
    try {
        execFileSync(stylelintBin, [
            file,
            '--config', path.join(repoRoot, '.stylelintrc.json'),
            '--allow-empty-input',
        ], { encoding: 'utf8' });
        return 0;
    } catch (error) {
        const output = `${error.stdout || ''}${error.stderr || ''}`;
        return (output.match(/ol\/import-at-top/g) || []).length;
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
}

describe('ol/import-at-top', () => {
    test('allows imports at the top of the file', () => {
        const warnings = lintImportAtTop(
            '@charset "utf-8";\n'
            + '@import "a.css";\n'
            + '@import "b.css" screen and (min-width: 1px);\n'
            + '.foo { color: red; }\n'
        );
        expect(warnings).toBe(0);
    });

    test('allows a blockless @layer statement before imports', () => {
        const warnings = lintImportAtTop(
            '@layer reset;\n'
            + '@import "a.css";\n'
            + '.foo { color: red; }\n'
        );
        expect(warnings).toBe(0);
    });

    test('flags an @import after a rule', () => {
        const warnings = lintImportAtTop(
            '.foo { color: red; }\n'
            + '@import "a.css";\n'
        );
        expect(warnings).toBe(1);
    });

    test('flags an @import after a rule even with a leading @charset', () => {
        const warnings = lintImportAtTop(
            '@charset "utf-8";\n'
            + '.foo { color: red; }\n'
            + '@import "a.css";\n'
        );
        expect(warnings).toBe(1);
    });

    test('flags an @import nested inside an at-rule', () => {
        const warnings = lintImportAtTop(
            '@media (min-width: 1px) {\n'
            + '  @import "a.css";\n'
            + '}\n'
        );
        expect(warnings).toBe(1);
    });
});
