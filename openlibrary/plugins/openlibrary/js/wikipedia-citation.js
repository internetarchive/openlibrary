import { copyText } from './copy-text.js';

export function initWikipediaCitation() {
    for (const button of document.querySelectorAll('[data-wikipedia-citation-copy]')) {
        const code = button.closest('.wikipedia-citation-popover__well').querySelector('code');
        button.addEventListener('click', () => copyText(button, code.textContent.trim()));
    }
}
