import i18nFactory from 'gettext.js';

const i18n = i18nFactory();

if (window.__OL_I18N__) {
    i18n.loadJSON(window.__OL_I18N__, 'messages');
}

export const _ = (s, ...args) => i18n.__(s, ...args);
export const _n = (s, plural, n, ...args) => i18n._n(s, plural, n, ...args);
