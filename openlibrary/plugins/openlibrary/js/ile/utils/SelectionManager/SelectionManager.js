// @ts-check
import $ from 'jquery';
import { move_to_work, move_to_author } from '../ol.js';
import './SelectionManager.less';

/**
 * The SelectionManager is responsible for making things (e.g. books in search results,
 * or authors on books pages) on Open Library selectable and drag/droppable from one
 * Open Library window to another.
 */
export default class SelectionManager {
    /**
     * @param {import('../../index.js').IntegratedLibrarianEnvironment} ile
     */
    constructor(ile, curpath=location.pathname) {
        this.ile = ile;
        this.curpath = curpath;
        this.inited = false;

        this.toggleSelected = this.toggleSelected.bind(this);
        this.dragStart = this.dragStart.bind(this);
        this.onDrop = this.onDrop.bind(this);
        this.allowDrop = this.allowDrop.bind(this);
    }

    init() {
        this.inited = true;

        // Label each selectable element with a class, and bind the click event
        const providers = this.getPossibleProviders();
        const providerSelectors = providers.map(p => p.selector);
        $(providerSelectors.join(', '))
            .addClass('ile-selectable')
            .on('click', this.toggleSelected);

        // Some providers need a "handle" to allow dragging.
        for (const provider of providers) {
            if (provider.addHandle) {
                for (const el of $(provider.selector).toArray()) {
                    const handle = $('<span class="ile-select-handle">&bull;</span>');
                    handle[0].addEventListener('click', ev => ev.preventDefault(), { capture: true });
                    $(el).prepend(handle);
                }
            }
        }

        // Add the drag/drop handlers to the main white part of the page
        document.getElementById('test-body-mobile').addEventListener('drop', this.onDrop);
        document.getElementById('test-body-mobile').addEventListener('dragover', this.allowDrop);
    }

    /**
     * @param {MouseEvent & { currentTarget: HTMLElement }} clickEvent
     */
    toggleSelected(clickEvent) {
        const el = clickEvent.currentTarget;
        el.classList.toggle('ile-selected');
        const selected = el.classList.contains('ile-selected');
        el.draggable = selected;
        const provider = this.getProvider(el);
        // FIXME: this is a bug if we support selecting multiple types
        const count = $('.ile-selected').length;
        this.ile.setStatusText(`${count} ${count === 1 ? provider.singular : provider.plural} selected`);
        $('#ile-drag-actions').empty();
        const img_src = provider.image(el);

        const actions = SelectionManager.ACTIONS.filter(a => (
            a.applies_to_type === provider.singular &&
            (a.multiple_only ? count > 1 : count > 0)
        ));
        const items = this.getSelectedItems();
        for (const action of actions) {
            $('#ile-drag-actions').append($(`<a target="_blank" href="${action.href(items)}">${action.name}</a>`));
        }

        if (selected) {
            el.addEventListener('dragstart', this.dragStart);
            const factor = -sigmoid($('#ile-drag-status .images img').length) + 1 + 0.5;
            $('#ile-drag-status .images').append(`<img src="${img_src}" style="padding: ${(1 - factor) * 5}px 0; width: ${(factor ** 3) * 100}%"/>`);
        } else {
            el.removeEventListener('dragstart', this.dragStart);
            const img_el = $('#ile-drag-status .images img').toArray().find(el => el.src === img_src);
            $(img_el).remove();
        }
    }

    /**
     * @param {DragEvent} ev
     */
    dragStart(ev) {
        const selected = $('.ile-selected').toArray();
        if (selected.length > 1) {
            ev.dataTransfer.setDragImage($('#ile-drag-status')[0], 0, 0);
        }
        const data = {
            from: this.curpath.match(/OL\d+[AWM]/)[0],
            items: this.getSelectedItems()
        };
        ev.dataTransfer.setData('text', JSON.stringify(data));
    }

    getSelectedItems() {
        return $('.ile-selected').toArray().map(el => this.getProvider(el).data(el));
    }

    /**
     * @param {DragEvent} ev
     */
    onDrop(ev) {
        ev.preventDefault();
        const handler = this.getHandler();
        const data = JSON.parse(ev.dataTransfer.getData('text'));
        handler.ondrop(data);
    }

    /**
     * @param {DragEvent} ev
     */
    allowDrop(ev) {
        const handler = this.getHandler();
        if ($('.ile-selected').length || !handler) return;

        ev.preventDefault();
        this.ile.setStatusText(handler.message);
        document.getElementById('test-body-mobile').classList.add('ile-drag-over');
    }

    getHandler() {
        return SelectionManager.DROP_HANDLERS.find(h => h.path.test(this.curpath));
    }

    getPossibleProviders() {
        return SelectionManager.SELECTION_PROVIDERS.filter(p => p.path.test(this.curpath));
    }

    /**
     * @param {HTMLElement} el
     */
    getProvider(el) {
        return SelectionManager.SELECTION_PROVIDERS
            .find(p => p.path.test(this.curpath) && el.matches(p.selector));
    }
}


/**
 * Drop handlers define patterns for how certain drops should be handled.
 * Currently there's no way to match based on what's being dropped, only
 * where.
 */
SelectionManager.DROP_HANDLERS = [
    /** Dropping books from one author to another */
    {
        path: /\/authors\/OL\d+A.*/,
        message: 'Move to this author',
        async ondrop(data) {
            // eslint-disable-next-line no-console
            console.log('move', data);
            window.ILE.setStatusText('Working...');
            try {
                await move_to_author(data.items, data.from, location.pathname.match(/OL\d+A/)[0]);
                window.ILE.setStatusText('Completed!');
            } catch (e) {
                window.ILE.setStatusText('Errored!');
                throw e;
            }
        }
    },
    /** Dropping editions from one work to another */
    {
        path: /(\/works\/OL\d+W.*|\/books\/OL\d+M.*)/,
        message: 'Move to this work',
        async ondrop(data) {
            // eslint-disable-next-line no-console
            console.log('move', data);
            window.ILE.setStatusText('Working...');
            try {
                let workOlid = location.pathname.match(/OL\d+W/)?.[0];
                if (!workOlid) {
                    const ed = await fetch(`/books/${location.pathname.match(/OL\d+M/)[0]}.json`).then(r => r.json());
                    workOlid = ed.works[0].key.match(/OL\d+W/)[0];
                }
                await move_to_work(data.items, data.from, workOlid);
                window.ILE.setStatusText('Completed!');
            } catch (e) {
                window.ILE.setStatusText('Errored!');
                throw e;
            }
        }
    },
];

/**
 * Selection Providers define what is selectable on a page. E.g. the path regex
 * determines the url to apply the selection provider to.
 */
SelectionManager.SELECTION_PROVIDERS = [
    /**
     * This selection provider makes books in search results selectable.
     */
    {
        path: /(\/authors\/OL\d+A.*|\/search)/,
        selector: '.searchResultItem',
        image: el => $(el).find('.bookcover img')[0].src,
        singular: 'work',
        plural: 'works',
        /**
         * @param {HTMLElement} el
         * @return {import('../ol.js').WorkOLID}
         **/
        data: el => $(el).find('.booktitle a')[0].href.match(/OL\d+W/)[0],
    },
    /**
     * This selection provider makes editions in the editions table selectable.
     */
    {
        path: /(\/works\/OL\d+W.*|\/books\/OL\d+M.*)/,
        selector: '.book',
        image: el => $(el).find('.cover img')[0].src,
        singular: 'edition',
        plural: 'editions',
        /**
         * @param {HTMLElement} el
         * @return {import('../ol.js').EditionOLID}
         **/
        data: el => $(el).find('.title a')[0].href.match(/OL\d+M/)[0],
    },
    /**
     * This selection provider makes author names on the books page selectable.
     */
    {
        path: /(\/works\/OL\d+W.*|\/books\/OL\d+M.*)/,
        selector: 'a[href^="/authors/OL"]',
        addHandle: true,
        image: el => `https://covers.openlibrary.org/a/olid/${el.href.match(/OL\d+A/)[0]}-M.jpg?default=https://openlibrary.org/images/icons/avatar_author-lg.png`,
        singular: 'author',
        plural: 'authors',
        /**
         * @param {HTMLAnchorElement} el
         * @return {import('../ol.js').AuthorOLID}
         **/
        data: el => el.href.match(/OL\d+A/)[0],
    },
];

/**
 * Actions get enabled when a certain selections are made.
 */
SelectionManager.ACTIONS = [
    {
        applies_to_type: 'work',
        multiple_only: true,
        name: 'Merge Works...',
        href: olids => `/works/merge?records=${olids.join(',')}`,
    },
    {
        // Someday, anyways!
        applies_to_type: 'edition',
        multiple_only: true,
        name: 'Merge Editions...',
        href: olids => `/works/merge?records=${olids.join(',')}`,
    },
    {
        applies_to_type: 'author',
        multiple_only: true,
        name: 'Merge Authors...',
        href: olids => `https://openlibrary.org/authors/merge?${olids.map(olid => `key=${olid}`).join('&')}`,
    },
];

function sigmoid(x) {
    return Math.exp(x) / (Math.exp(x) + 1);
}
