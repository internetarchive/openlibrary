import {
    jqueryUiAmdDeps,
    injectJqueryGlobals,
    chunkName,
    CHUNK_NAME_MAP,
} from 'vite-js-plugins.mjs';

describe('injectJqueryGlobals', () => {
    const plugin = injectJqueryGlobals();
    const projectFile = (name = 'foo.js') => `/repo/openlibrary/plugins/openlibrary/js/${name}`;
    const result = (code, id) => plugin.transform(code, id);
    const injected = (code, id) => result(code, id)?.code;

    test('injects `import $` when code uses bare `$(`', () => {
        const code = '$(document).ready(function () {});';
        expect(injected(code, projectFile())).toBe(`import $ from 'jquery';\n${code}`);
    });

    test('injects `import jQuery` when code uses bare `jQuery`', () => {
        const code = 'jQuery.each([1, 2], function () {});';
        expect(injected(code, projectFile())).toBe(`import jQuery from 'jquery';\n${code}`);
    });

    test('injects both as separate statements when both identifiers are used', () => {
        const code = '$("div").hide();\njQuery("span").show();';
        const out = injected(code, projectFile());
        expect(out).toContain('import $ from \'jquery\';');
        expect(out).toContain('import jQuery from \'jquery\';');
    });

    test('leaves modules that already import jquery alone', () => {
        const code = 'import $ from \'jquery\';\n$(\'div\').hide();';
        expect(result(code, projectFile())).toBeNull();
    });

    test('leaves modules that declare their own `$` binding alone', () => {
        const code = 'const $ = function () {};\n$(\'x\');';
        expect(result(code, projectFile())).toBeNull();
    });

    test('does not treat `$foo` as the jquery identifier', () => {
        const code = 'const $foo = 1;\nconsole.log($foo);';
        expect(result(code, projectFile())).toBeNull();
    });

    test('leaves node_modules untouched', () => {
        const code = '$("x");';
        expect(result(code, '/repo/node_modules/jquery-ui/ui/widgets/tabs.js')).toBeNull();
    });

    test('returns null for files with no jquery usage', () => {
        const code = 'export const x = 1;';
        expect(result(code, projectFile())).toBeNull();
    });
});

describe('jqueryUiAmdDeps', () => {
    const plugin = jqueryUiAmdDeps();
    const uiFile = (name = 'tabs.js') => `/repo/node_modules/jquery-ui/ui/widgets/${name}`;
    const result = (code, id) => plugin.transform(code, id);
    const injected = (code, id) => result(code, id)?.code;

    test('injects side-effect imports for relative AMD deps, in order', () => {
        const code = 'define(["jquery", "../widget", "../position"], factory);';
        const out = injected(code, uiFile());
        expect(out).not.toBeNull();
        expect(out).toContain('import \'/repo/node_modules/jquery-ui/ui/widget.js\';');
        expect(out).toContain('import \'/repo/node_modules/jquery-ui/ui/position.js\';');
        // jquery itself is a window global — not imported
        expect(out).not.toContain('jquery.js');
    });

    test('returns null for non-jquery-ui files', () => {
        expect(result('define(["a"], factory);', '/repo/openlibrary/plugins/openlibrary/js/foo.js')).toBeNull();
    });

    test('returns null when there is no AMD define', () => {
        expect(result('const x = 1;', uiFile())).toBeNull();
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
