import { sprintf } from '../../../openlibrary/plugins/openlibrary/js/i18n.js';

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
        document.head.innerHTML = catalog ? `<script type="application/json" id="ol-js-i18n">${JSON.stringify(catalog)}</script>` : '';
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
});
