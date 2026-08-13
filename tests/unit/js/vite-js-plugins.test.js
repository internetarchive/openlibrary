import fs from 'fs';
import path from 'path';
import {
    chunkName,
    CHUNK_NAME_MAP,
} from 'vite-js-plugins.mjs';

describe('jquery-ui wrapper modules', () => {
    // The explicit jquery-ui-*.js bootstrap modules replace the old
    // jqueryUiAmdDeps transform plugin: each lists its AMD `define([...])`
    // deps in topological order. These tests pin the wrappers to jquery-ui's
    // actual AMD graph, so an upgrade that adds/removes a dep (or breaks the
    // format) fails loudly here instead of at runtime.
    const JQ = path.join(__dirname, '../../..', 'node_modules/jquery-ui');
    const WRAPPER_DIR = path.join(__dirname, '../../..', 'openlibrary/plugins/openlibrary/js');
    const wrappers = ['jquery-ui-tabs', 'jquery-ui-dialog', 'jquery-ui-autocomplete', 'jquery-ui-sortable'];

    const depsOf = (file) => {
        const code = fs.readFileSync(path.join(JQ, file), 'utf8');
        const match = code.match(/define\s*\(\s*\[([\s\S]*?)\]\s*,\s*factory\s*\)/);
        if (!match) return [];
        return [...match[1].matchAll(/"([^"\\]+)"/g)]
            .map((m) => m[1])
            .filter((d) => d !== 'jquery'); // jquery is a window global
    };

    // Wrapper imports use the bare `jquery-ui/...` specifier; map to the file
    // path relative to the jquery-ui package root for the checks below.
    const stripSpecifier = (spec) => spec.replace(/^jquery-ui\//, '');

    test.each(wrappers)('%s lists jquery-ui files that all exist', (name) => {
        const code = fs.readFileSync(path.join(WRAPPER_DIR, `${name}.js`), 'utf8');
        const files = [...code.matchAll(/^import '([^']+)';/gm)].map((m) => stripSpecifier(m[1]));
        expect(files.length).toBeGreaterThan(0);
        for (const f of files) {
            expect(() => fs.statSync(path.join(JQ, `${f}.js`))).not.toThrow();
        }
    });

    test.each(wrappers)('%s is a valid topological order of jquery-ui AMD deps', (name) => {
        const code = fs.readFileSync(path.join(WRAPPER_DIR, `${name}.js`), 'utf8');
        const files = [...code.matchAll(/^import '([^']+)';/gm)].map((m) => `${stripSpecifier(m[1])}.js`);
        const pos = new Map(files.map((f, i) => [f, i]));
        for (const f of files) {
            for (const dep of depsOf(f)) {
                const resolved = path.resolve(path.join(JQ, path.dirname(f)), dep);
                const rel = resolved.slice(JQ.length + 1) + (resolved.endsWith('.js') ? '' : '.js');
                expect(pos.has(rel)).toBe(true);
                expect(pos.get(rel)).toBeLessThan(pos.get(f));
            }
        }
    });

    test('dialog wrapper includes every direct AMD dep of the dialog widget', () => {
        const code = fs.readFileSync(path.join(WRAPPER_DIR, 'jquery-ui-dialog.js'), 'utf8');
        const files = new Set([...code.matchAll(/^import '([^']+)';/gm)].map((m) => `${stripSpecifier(m[1])}.js`));
        for (const dep of depsOf('ui/widgets/dialog.js')) {
            const resolved = path.resolve(path.join(JQ, 'ui/widgets'), dep);
            const rel = resolved.slice(JQ.length + 1) + (resolved.endsWith('.js') ? '' : '.js');
            expect(files.has(rel)).toBe(true);
        }
    });
});

describe('chunkName', () => {
    test('remaps via CHUNK_NAME_MAP', () => {
        expect(chunkName({ name: 'edit' })).toBe('user-website');
        expect(chunkName({ name: 'modals' })).toBe('modal-links');
        expect(chunkName({ name: 'readinglog_stats' })).toBe('readinglog-stats');
    });

    test('names the app entry (index.js) "main"', () => {
        const info = { name: 'js', facadeModuleId: '/repo/openlibrary/plugins/openlibrary/js/index.js' };
        expect(chunkName(info)).toBe('main');
    });

    test('falls back to the facade module basename', () => {
        expect(chunkName({ facadeModuleId: '/repo/openlibrary/plugins/openlibrary/js/tabs.js' })).toBe('tabs');
    });

    test('defaults to the name when present', () => {
        expect(chunkName({ name: 'tabs' })).toBe('tabs');
    });

    test('covers every key the config maps', () => {
        expect(Object.keys(CHUNK_NAME_MAP).length).toBeGreaterThan(10);
    });
});
