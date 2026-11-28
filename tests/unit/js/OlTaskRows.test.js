/**
 * Unit tests for <ol-task-book> and <ol-task-rows>, the Tasks pages' book cards.
 * Both render into the light DOM. Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlTaskRows.js';

beforeAll(() => {
    // ol-tooltip reads matchMedia to detect a hover-capable pointer.
    window.matchMedia = query => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {}
    });
});

const BOOK = {
    key: '/books/OL1M',
    olid: 'OL1M',
    edit_url: '/books/OL1M/edit',
    title: 'A Book',
    authors: 'An Author',
    cover_url: null,
    edition_line: 'A Publisher · 2001',
    isbn13: '9780000000000',
    edition_count: 3,
    work_key: '/works/OL1W',
    readers: null
};
const TASKS = [
    { key: 'OL1M/covers', field: 'covers', label: 'Cover', action_label: 'Add a cover', url: '/tasks/task/OL1M/covers' },
    { key: 'OL1M/lccn', field: 'lccn', label: 'LCCN', action_label: 'Add the LCCN', url: '/tasks/task/OL1M/lccn' }
];
const ROWS = [{ book: BOOK, tasks: TASKS }];

const response = (status, body) => ({ ok: status < 400, status, json: async () => body });

function mountRows(attrs, placeholder = '<ol class="contrib-rows"><li data-placeholder></li></ol>') {
    const el = document.createElement('ol-task-rows');
    for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, value);
    el.innerHTML = placeholder;
    document.body.appendChild(el);
    return el;
}

describe('ol-task-book', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
    });

    test('replaces its placeholders with the book and its tasks on upgrade, in the light DOM', () => {
        document.body.innerHTML = `<ol-task-book compact task-track="TaskDone|SameBookTask"
            book='${JSON.stringify(BOOK)}' tasks='${JSON.stringify(TASKS)}'><div data-placeholder></div></ol-task-book>`;
        const el = document.querySelector('ol-task-book');
        expect(el.shadowRoot).toBeNull();
        expect(el.querySelector('[data-placeholder]')).toBeNull();
        expect(el.querySelector('.contrib-book--compact .contrib-book__title a').textContent).toBe('A Book');
        expect(el.querySelector('.contrib-book__line').textContent).toContain('one of 3 editions of this work');
        expect([...el.querySelectorAll('[data-task-key]')].map(li => li.dataset.taskKey)).toEqual(['OL1M/covers', 'OL1M/lccn']);
        expect(el.querySelector('[data-task-key="OL1M/lccn"] a').dataset.olLinkTrack).toBe('TaskDone|SameBookTask|lccn');
    });

    test('leads to the book page with no view and edit buttons by default, and no task list without tasks', async () => {
        const el = document.createElement('ol-task-book');
        el.book = BOOK;
        document.body.appendChild(el);
        await el.updateComplete;
        expect(el.querySelector('.contrib-book__title a').getAttribute('href')).toBe('/books/OL1M');
        expect(el.querySelector('.contrib-book__title a').hasAttribute('data-ol-link-track')).toBe(false);
        expect(el.querySelector('.contrib-book__actions')).toBeNull();
        expect(el.querySelector('.contrib-row__tasks')).toBeNull();
    });

    test('a link elsewhere adds buttons to the book, labelled from the translations given', async () => {
        const el = document.createElement('ol-task-book');
        Object.assign(el, { book: BOOK, href: '/tasks/task/OL1M/covers', labels: { viewBook: 'Voir le livre' } });
        document.body.appendChild(el);
        await el.updateComplete;
        const buttons = el.querySelectorAll('.contrib-book__actions ol-button');
        expect([...buttons].map(b => b.getAttribute('href'))).toEqual(['/books/OL1M', '/books/OL1M/edit']);
        expect(buttons[0].getAttribute('aria-label')).toBe('Voir le livre');
        expect(buttons[1].getAttribute('aria-label')).toBe('Go to edit page');
    });
});

describe('ol-task-rows', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        global.fetch = vi.fn();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('renders inline rows as cards whose title opens the first task, and fires a render event', async () => {
        const onRender = vi.fn();
        document.addEventListener('ol-task-rows-render', onRender, { once: true });
        const el = mountRows({ rows: JSON.stringify(ROWS), 'title-track': 'TasksDashboard|OpenTaskTitle', 'task-track': 'TasksDashboard|OpenTask' });
        await el.updateComplete;
        await el.querySelector('ol-task-book').updateComplete;
        expect(el.querySelector('[data-placeholder]')).toBeNull();
        expect(el.querySelectorAll('.contrib-rows > [data-book-row]')).toHaveLength(1);
        const title = el.querySelector('.contrib-book__title a');
        expect(title.getAttribute('href')).toBe('/tasks/task/OL1M/covers');
        expect(title.dataset.olLinkTrack).toBe('TasksDashboard|OpenTaskTitle|covers');
        expect(el.querySelector('[data-task-key="OL1M/covers"] a').dataset.olLinkTrack).toBe('TasksDashboard|OpenTask|covers');
        expect(onRender).toHaveBeenCalledWith(expect.objectContaining({ detail: { count: 1 } }));
        expect(global.fetch).not.toHaveBeenCalled();
    });

    test('keeps its placeholders up while the server answers 202, then renders the fetched rows', async () => {
        vi.useFakeTimers();
        global.fetch.mockResolvedValueOnce(response(202)).mockResolvedValueOnce(response(200, { rows: ROWS }));
        const el = mountRows({ src: '/tasks/rows.json?task=covers' });
        await vi.advanceTimersByTimeAsync(0);
        expect(el.querySelector('[data-placeholder]')).not.toBeNull();
        await vi.advanceTimersByTimeAsync(1000);
        await el.updateComplete;
        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(global.fetch.mock.calls[0][0]).toBe('/tasks/rows.json?task=covers');
        expect(el.querySelector('[data-placeholder]')).toBeNull();
        expect(el.querySelectorAll('[data-book-row]')).toHaveLength(1);
    });

    test('an error status removes the placeholders and fires an error event, without retrying', async () => {
        global.fetch.mockResolvedValue(response(500));
        const onError = vi.fn();
        document.addEventListener('ol-task-rows-error', onError, { once: true });
        const el = mountRows({ src: '/tasks/rows.json' });
        await vi.waitFor(() => expect(onError).toHaveBeenCalled());
        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(el.querySelector('[data-placeholder]')).toBeNull();
        expect(el.querySelector('[data-book-row]')).toBeNull();
    });
});
