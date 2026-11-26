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
    async function withCatalog(catalog) {
        window.OL_I18N = catalog ?? undefined;
        vi.resetModules();
        return import('../../../openlibrary/plugins/openlibrary/js/i18n.js');
    }

    it('translates from the page catalog, falling back to the English', async () => {
        const { _ } = await withCatalog({ Advanced: 'Avanzado' });
        expect(_('Advanced')).toBe('Avanzado');
        expect(_('Not in the catalog')).toBe('Not in the catalog');
    });

    it('picks the plural form for the count, falling back to the English', async () => {
        const { ngettext } = await withCatalog({ '%(count)s list': { one: '%(count)s lista', other: '%(count)s listas' } });
        expect(ngettext('%(count)s list', '%(count)s lists', 1)).toBe('%(count)s lista');
        expect(ngettext('%(count)s list', '%(count)s lists', 3)).toBe('%(count)s listas');
        expect(ngettext('%(count)s book', '%(count)s books', 1)).toBe('%(count)s book');
        expect(ngettext('%(count)s book', '%(count)s books', 2)).toBe('%(count)s books');
    });

    it('shows the English when the page has no catalog', async () => {
        const { _ } = await withCatalog(null);
        expect(_('Advanced')).toBe('Advanced');
    });

    it('calls a function label with the count and fills its placeholders', async () => {
        const { ngettext, translate } = await withCatalog({ '%(count)s item': { one: '%(count)s elemento', other: '%(count)s elementos' } });
        const defaults = { items: count => ngettext('%(count)s item', '%(count)s items', count) };
        expect(translate(null, defaults, 'items', { count: 1 })).toBe('1 elemento');
        expect(translate(null, defaults, 'items', { count: 4 })).toBe('4 elementos');
    });
});
