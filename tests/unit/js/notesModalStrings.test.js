import {
    DEFAULT_NOTES_MODAL_STRINGS,
    notesModalStrings,
} from '../../../openlibrary/plugins/openlibrary/js/modals';

// jquery-colorbox needs browser globals jsdom doesn't provide, and the strings
// reader under test never touches it.
vi.mock('jquery-colorbox', () => ({}));

describe('notesModalStrings', () => {
    function elementWith(dataI18n) {
        const el = document.createElement('div');
        if (dataI18n !== undefined) {
            el.setAttribute('data-i18n', dataI18n);
        }
        return el;
    }

    test('returns the English defaults when the attribute is missing', () => {
        expect(notesModalStrings(elementWith(undefined))).toBe(DEFAULT_NOTES_MODAL_STRINGS);
    });

    test('returns the English defaults when given no element', () => {
        expect(notesModalStrings(null)).toBe(DEFAULT_NOTES_MODAL_STRINGS);
    });

    test('uses the translated strings when the attribute is valid', () => {
        const el = elementWith(JSON.stringify({
            saveSuccess: 'Note enregistrée.',
            deleteSuccess: 'Note supprimée.',
        }));
        expect(notesModalStrings(el).saveSuccess).toBe('Note enregistrée.');
        expect(notesModalStrings(el).deleteSuccess).toBe('Note supprimée.');
    });

    test('keeps the English text for keys a locale has not translated', () => {
        const el = elementWith(JSON.stringify({ saveSuccess: 'Note enregistrée.' }));
        const strings = notesModalStrings(el);
        expect(strings.saveSuccess).toBe('Note enregistrée.');
        expect(strings.deleteError).toBe(DEFAULT_NOTES_MODAL_STRINGS.deleteError);
    });

    test('falls back to the defaults when the attribute is not valid JSON', () => {
        expect(notesModalStrings(elementWith('{not json'))).toBe(DEFAULT_NOTES_MODAL_STRINGS);
    });
});
