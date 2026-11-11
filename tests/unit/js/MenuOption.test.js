import { describe, test, expect } from 'vitest';
import { MenuOption, MenuOptionState } from '../../../openlibrary/plugins/openlibrary/js/bulk-tagger/BulkTagger/MenuOption.js';

// GHSA-6xcf: MenuOption rendered tag data into `parentElem.innerHTML`. tagName
// and displayType are user-controlled, so an HTML payload would execute. The
// fix builds the option with safe DOM construction; these prove the payload is
// rendered as inert text, never parsed into live elements.
describe('MenuOption.createMenuOption (GHSA-6xcf DOM-XSS)', () => {
    test('renders a malicious tagName as text, not markup', () => {
        const payload = '<img src=x onerror="window.__xss=1">';
        const opt = new MenuOption({ tagName: payload, tagType: 'subjects', displayType: 'Subject' }, MenuOptionState.NONE_TAGGED, 0);
        opt.createMenuOption();
        const root = opt.rootElement;
        expect(root.querySelector('img')).toBeNull();
        expect(root.querySelector('.selected-tag__name').textContent).toBe(payload);
    });

    test('renders a malicious displayType as text, not markup', () => {
        const payload = '<svg onload="window.__xss=1"></svg>';
        const opt = new MenuOption({ tagName: 'ok', tagType: 'subjects', displayType: payload }, MenuOptionState.ALL_TAGGED, 1);
        opt.createMenuOption();
        const root = opt.rootElement;
        expect(root.querySelector('svg')).toBeNull();
        expect(root.querySelector('.selected-tag__type').textContent).toBe(payload);
    });

    test('still renders the expected structure for benign data', () => {
        const opt = new MenuOption({ tagName: 'Fiction', tagType: 'subjects', displayType: 'Subject' }, MenuOptionState.NONE_TAGGED, 0);
        opt.createMenuOption();
        const root = opt.rootElement;
        expect(root.querySelector('.selected-tag__name').textContent).toBe('Fiction');
        expect(root.querySelector('.selected-tag__type').textContent).toBe('Subject');
        expect(root.querySelector('.selected-tag__type').className).toContain('selected-tag__type--subject');
    });
});
