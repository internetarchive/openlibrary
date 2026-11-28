/**
 * The Cookbook's builder recipe (/developers/design/cookbook/builder): an
 * autocomplete that adds rows to a list. It filters the sample books the page
 * carries in `data-books`, so nothing is fetched and nothing is saved.
 */

const MAX_OPTIONS = 6;

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function renderOption(book, index) {
    const option = el('li', 'ol-combobox__option');
    option.id = `cb-list-option-${index}`;
    option.setAttribute('role', 'option');
    option.setAttribute('aria-selected', 'false');

    const thumb = el('img', 'ol-combobox__thumb');
    thumb.src = book.cover;
    thumb.alt = '';
    thumb.loading = 'lazy';

    const text = el('span', 'ol-combobox__text');
    text.append(el('span', 'ol-combobox__label', book.title), el('span', 'ol-combobox__meta', `${book.author} · ${book.year}`));
    option.append(thumb, text);
    return option;
}

function renderItem(book) {
    const item = el('li', 'ol-item ol-item--new');
    item.dataset.title = book.title;

    const media = el('div', 'ol-item__media');
    const cover = document.createElement('ol-book-cover');
    cover.setAttribute('src', book.cover);
    cover.setAttribute('book-title', book.title);
    cover.setAttribute('authors', book.author);
    cover.setAttribute('size', 'small');
    cover.toggleAttribute('no-tip', true);
    media.append(cover);

    const text = el('div', 'ol-item__text');
    const meta = el('p', 'ol-meta-line');
    meta.append(el('span', '', book.author), el('span', '', String(book.year)));
    text.append(el('div', 'ol-item__title', book.title), meta);

    const actions = el('div', 'ol-item__actions');
    const remove = document.createElement('ol-button');
    remove.setAttribute('variant', 'ghost');
    remove.setAttribute('shape', 'icon');
    remove.setAttribute('aria-label', `Remove ${book.title}`);
    remove.toggleAttribute('data-builder-remove', true);
    const icon = document.createElement('ol-icon');
    icon.setAttribute('name', 'x');
    remove.append(icon);
    actions.append(remove);

    item.append(media, text, actions);
    return item;
}

export function initCookbookBuilder(form) {
    const books = JSON.parse(form.dataset.books || '[]');
    const input = form.querySelector('[data-builder-input]');
    const panel = form.querySelector('[data-builder-options]');
    const list = form.querySelector('[data-builder-list]');
    const empty = form.querySelector('[data-builder-empty]');
    const count = form.querySelector('[data-builder-count]');

    let matches = [];
    let active = -1;

    const added = () => new Set([...list.children].map(item => item.dataset.title));

    function sync() {
        const total = list.children.length;
        empty.hidden = total > 0;
        list.hidden = total === 0;
        count.hidden = total === 0;
        count.textContent = total === 1 ? '1 book' : `${total} books`;
    }

    function close() {
        panel.hidden = true;
        panel.replaceChildren();
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        matches = [];
        active = -1;
    }

    function setActive(index) {
        active = index;
        [...panel.children].forEach((option, i) => option.setAttribute('aria-selected', String(i === index)));
        const option = panel.children[index];
        if (option) {
            input.setAttribute('aria-activedescendant', option.id);
            option.scrollIntoView({ block: 'nearest' });
        }
    }

    function open() {
        const query = input.value.trim().toLowerCase();
        if (!query) return close();
        const taken = added();
        matches = books.filter(book => !taken.has(book.title) && `${book.title} ${book.author}`.toLowerCase().includes(query)).slice(0, MAX_OPTIONS);
        panel.replaceChildren(...(matches.length ? matches.map(renderOption) : [el('li', 'ol-combobox__none', 'No matching books')]));
        panel.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        if (matches.length) setActive(0);
    }

    function add(book) {
        list.append(renderItem(book));
        input.value = '';
        close();
        sync();
        input.focus();
    }

    input.addEventListener('input', open);
    input.addEventListener('focus', open);
    input.addEventListener('blur', close);
    input.addEventListener('keydown', event => {
        if (event.key === 'Escape') return close();
        if (!matches.length) return;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const step = event.key === 'ArrowDown' ? 1 : -1;
            setActive((active + step + matches.length) % matches.length);
        } else if (event.key === 'Enter') {
            // Enter picks the highlighted book; it must not submit the form.
            event.preventDefault();
            add(matches[active]);
        }
    });

    // mousedown, not click: the input's blur closes the panel before a click lands.
    panel.addEventListener('mousedown', event => {
        event.preventDefault();
        const option = event.target.closest('[role="option"]');
        if (option) add(matches[[...panel.children].indexOf(option)]);
    });

    list.addEventListener('click', event => {
        const remove = event.target.closest('[data-builder-remove]');
        if (!remove) return;
        remove.closest('.ol-item').remove();
        sync();
        input.focus();
    });

    form.addEventListener('submit', event => event.preventDefault());

    sync();
}
