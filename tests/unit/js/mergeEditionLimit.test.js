import { DEFAULT_EDITION_LIMIT, isEditionListTruncated } from '../../../openlibrary/components/MergeUI/utils.js';

describe('isEditionListTruncated', () => {
    it('allows a low edition count when the reported total is stale', () => {
        expect(isEditionListTruncated({ entries: [{}, {}], size: DEFAULT_EDITION_LIMIT + 1 })).toBe(false);
    });

    it('blocks when the response is full and more editions exist', () => {
        const entries = Array.from({ length: DEFAULT_EDITION_LIMIT });

        expect(isEditionListTruncated({ entries, size: DEFAULT_EDITION_LIMIT + 1 })).toBe(true);
    });

    it('allows a complete response at the edition limit', () => {
        const entries = Array.from({ length: DEFAULT_EDITION_LIMIT });

        expect(isEditionListTruncated({ entries, size: DEFAULT_EDITION_LIMIT })).toBe(false);
    });
});
