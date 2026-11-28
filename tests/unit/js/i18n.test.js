import { fmt, sprintf } from '../../../openlibrary/plugins/openlibrary/js/i18n.js';

describe('fmt', () => {
    it('fills named placeholders in whatever order a translation puts them', () => {
        expect(fmt('%(sha)s : %(num)s commits', { num: 4, sha: 'abc1234' })).toBe('abc1234 : 4 commits');
    });
});

describe('sprintf', () => {
    it('fills %s placeholders in order', () => {
        expect(sprintf('%s of %s', 7, 10)).toBe('7 of 10');
    });

    it('fills %(name)s placeholders from an object', () => {
        expect(sprintf('Showing %(shown)s of %(total)s results', { shown: '7', total: '134,731' })).toBe('Showing 7 of 134,731 results');
    });

    it('turns %% into %', () => {
        expect(sprintf('%(percent)s%% done', { percent: 40 })).toBe('40% done');
    });
});

describe('_ and ngettext', () => {
    // `rule` is the Plural-Forms expression the page's catalog file would define.
    async function withCatalog(catalog, rule = 'n != 1') {
        window.OL_I18N = catalog ?? undefined;
        window.OL_I18N_PLURAL = catalog ? n => Number(new Function('n', `return (${rule});`)(n)) : undefined;
        vi.resetModules();
        return import('../../../openlibrary/plugins/openlibrary/js/i18n.js');
    }

    it('translates from the page catalog, falling back to the English', async () => {
        const { _ } = await withCatalog({ Advanced: 'Avanzado' });
        expect(_('Advanced')).toBe('Avanzado');
        expect(_('Not in the catalog')).toBe('Not in the catalog');
    });

    it('picks the plural form for the count, falling back to the English', async () => {
        const { ngettext } = await withCatalog({ '%(count)s list': ['%(count)s lista', '%(count)s listas'] });
        expect(ngettext('%(count)s list', '%(count)s lists', 1)).toBe('%(count)s lista');
        expect(ngettext('%(count)s list', '%(count)s lists', 3)).toBe('%(count)s listas');
        expect(ngettext('%(count)s book', '%(count)s books', 1)).toBe('%(count)s book');
        expect(ngettext('%(count)s book', '%(count)s books', 2)).toBe('%(count)s books');
    });

    it("uses the language's own Plural-Forms rule, as the server does", async () => {
        // Portuguese's .po rule is n != 1, so 0 takes the plural, unlike its CLDR "one" category.
        let { ngettext } = await withCatalog({ '%(count)s edition': ['%(count)s edição', '%(count)s edições'] });
        expect([0, 1, 2].map(n => ngettext('%(count)s edition', '%(count)s editions', n))).toEqual([
            '%(count)s edições',
            '%(count)s edição',
            '%(count)s edições'
        ]);

        // Russian has three forms.
        const ru = 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2';
        ({ ngettext } = await withCatalog({ '%(count)s book': ['один', 'несколько', 'много'] }, ru));
        expect([1, 3, 5, 11, 21, 22].map(n => ngettext('%(count)s book', '%(count)s books', n))).toEqual([
            'один',
            'несколько',
            'много',
            'много',
            'один',
            'несколько'
        ]);
    });

    it('shows the English when the rule points past the forms it has', async () => {
        const { ngettext } = await withCatalog({ '%(count)s list': ['%(count)s lista'] });
        expect(ngettext('%(count)s list', '%(count)s lists', 3)).toBe('%(count)s lists');
    });

    it('shows the English when the page has no catalog', async () => {
        const { _ } = await withCatalog(null);
        expect(_('Advanced')).toBe('Advanced');
    });

    it('lookup calls a count function and fills its placeholders', async () => {
        const { lookup, ngettext } = await withCatalog({ '%(count)s item': ['%(count)s elemento', '%(count)s elementos'] });
        const strings = { items: count => ngettext('%(count)s item', '%(count)s items', count) };
        expect(lookup(strings, 'items', { count: 1 })).toBe('1 elemento');
        expect(lookup(strings, 'items', { count: 4 })).toBe('4 elementos');
    });
});
