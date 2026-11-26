import { DEFAULT_EDITION_LIMIT, isEditionListTruncated } from '../../../openlibrary/components/MergeUI/utils.js';

describe('isEditionListTruncated', () => {
    it('allows a low edition count when the reported total is stale', () => {
        expect(isEditionListTruncated({ entries: [{}, {}], size: DEFAULT_EDITION_LIMIT + 1 })).toBe(false);
    });

    it('allows a complete response at the edition limit', () => {
        const entries = Array.from({ length: DEFAULT_EDITION_LIMIT });

        expect(isEditionListTruncated({ entries, size: DEFAULT_EDITION_LIMIT })).toBe(false);
    });

    it('blocks when more editions came back than a merge can move, even if the reported total is stale', () => {
        const entries = Array.from({ length: DEFAULT_EDITION_LIMIT + 1 });

        expect(isEditionListTruncated({ entries, size: DEFAULT_EDITION_LIMIT + 1 })).toBe(true);
        expect(isEditionListTruncated({ entries, size: 150 })).toBe(true);
    });
});
