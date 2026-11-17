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
