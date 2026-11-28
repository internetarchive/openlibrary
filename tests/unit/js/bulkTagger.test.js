import { renderBulkTagger } from '../../../openlibrary/plugins/openlibrary/js/bulk-tagger/index.js';

function render(catalog) {
    window.OL_I18N = catalog;
    const container = document.createElement('div');
    container.innerHTML = renderBulkTagger();
    return container;
}

afterEach(() => {
    delete window.OL_I18N;
});

describe('renderBulkTagger', () => {
    test('shows the English strings without a catalog', () => {
        const form = render(undefined);
        expect(form.querySelector('.form-header p').textContent).toBe('Manage Subjects');
        expect(form.querySelector('.subjects-search-input').placeholder).toBe('Filter subjects e.g. Epic');
        expect([...form.querySelectorAll('.subject-type-option')].map(el => el.textContent)).toEqual(['subject', 'person', 'place', 'time', 'collection']);
        expect(form.querySelector('.bulk-tagging-submit').textContent).toBe('Submit');
    });

    test('puts the subject name where the translation has its placeholder', () => {
        const form = render({ 'Create new subject %(name)s with type:': 'Crear el tema %(name)s, de tipo:' });
        const sentence = form.querySelector('.search-subject-row-name-create-p');
        form.querySelector('.subject-name').textContent = 'Elfos';
        expect(sentence.textContent).toBe('Crear el tema Elfos, de tipo:');
    });

    test('keeps the whole sentence when a translation drops the placeholder', () => {
        const form = render({ 'Create new subject %(name)s with type:': 'Nuevo tema, de tipo:' });
        const sentence = form.querySelector('.search-subject-row-name-create-p');
        expect(sentence.textContent).toBe('Nuevo tema, de tipo:');
        expect(sentence.innerHTML).not.toContain('undefined');
    });

    test('escapes translations before putting them in the markup', () => {
        const form = render({ 'Manage Subjects': '<b>Temas</b>', 'Filter subjects e.g. Epic': 'Filtrar "temas" & más' });
        expect(form.querySelector('.form-header p').textContent).toBe('<b>Temas</b>');
        expect(form.querySelector('.form-header b')).toBeNull();
        expect(form.querySelector('.subjects-search-input').placeholder).toBe('Filtrar "temas" & más');
    });
});
