// @ts-check
import $ from 'jquery';
import { move_to_work, move_to_author } from '../ol.js';
import './SelectionManager.less';

/**
 * The SelectionManager is responsible for making things (e.g. books in search results,
 * or authors on books pages) on Open Library selectable and drag/droppable from one
 * Open Library window to another.
 *
 * Selected items are stored in tab-specific storage until manually cleared, in an object
 * containing arrays of olids keyed by type: {'edition':['OL1M','OL2M'], 'work':[],...}
 * The work array may contain entries of the form OL3W:OL4M where the second value is the
 * id of the specific edition surfaced in a search result.
 */
export default class SelectionManager {
    /**
     * @param {import('../../index.js').IntegratedLibrarianEnvironment} ile
     */
    constructor(ile, curpath=location.pathname) {
        this.ile = ile;
        this.curpath = curpath;
        this.inited = false;
        this.selectedItems = {};
        this.lastClicked = null;

        this.processClick = this.processClick.bind(this);
        this.toggleSelected = this.toggleSelected.bind(this);
        this.clearSelectedItems = this.clearSelectedItems.bind(this);
        this.dragStart = this.dragStart.bind(this);
        this.dragEnd = this.dragEnd.bind(this);
        this.onDrop = this.onDrop.bind(this);
        this.allowDrop = this.allowDrop.bind(this);

        // Collator used to naturally order OLIDs before constructing URL
        this.collator = new Intl.Collator('en-US', {numeric: true});
    }

    init() {
        this.inited = true;
        this.getSelectedItems();

        // Label each selectable element with a class, and bind the click event
        const providers = this.getPossibleProviders();
        const providerSelectors = providers.map(p => p.selector);
        $(providerSelectors.join(', '))
            .addClass('ile-selectable')
            .on('click', this.processClick);

        for (const provider of providers) {
            for (const el of $(provider.selector).toArray()) {
                // Some providers need a "handle" to allow dragging.
                if (provider.addHandle) {
                    const handle = $('<span class="ile-select-handle">&bull;</span>');
                    handle[0].addEventListener('click', ev => ev.preventDefault(), { capture: true });
                    $(el).prepend(handle);
                }
                // Restore any stored selections on this page
                for (const type of provider.type) {
                    if (this.selectedItems[type].length) {
                        if (this.selectedItems[type].indexOf(provider.data(el)) !== -1) {
                            this.setElementSelectionAttributes(el, true);
                        }
                    }
                }
            }
        }

        // Populate the status bar images for stored selections
        for (const type of SelectionManager.TYPES) {
            this.selectedItems[type.singular].forEach(olid => {
                this.ile.$statusImages.append(`<li><img title="${olid}" src="${type.image(olid)}" /></li>`);
            });
        }

        this.updateToolbar();

        // Add the drag/drop handlers to the main white part of the page
        document.getElementById('test-body-mobile').addEventListener('drop', this.onDrop);
        document.getElementById('test-body-mobile').addEventListener('dragover', this.allowDrop);
    }

    /**
     * @param {MouseEvent & { currentTarget: HTMLElement }} clickEvent
     */
    processClick(clickEvent) {
        // If there is text selection or the click is on a link that isn't a select handle, don't do anything
        if ((!clickEvent.shiftKey && window.getSelection()?.toString() !== '') ||
            ($(clickEvent.target).closest('a, button').length > 0 &&
            $(clickEvent.target).not('.ile-select-handle').length > 0)) return;

        const el = clickEvent.currentTarget;
        if (clickEvent.shiftKey && this.lastClicked)
        {
            // clear selection ranges created by shift-clicking since they're not suppressed by preventDefault().
            clearTextSelection();
            const siblingSet = this.getSelectableRange(el);
            const lastClickedIndex = siblingSet.index(this.lastClicked);
            const elIndex = siblingSet.index(el);
            if (lastClickedIndex > -1 && Math.abs(elIndex - lastClickedIndex) > 1) {
                let affectedElements;
                if (elIndex > lastClickedIndex) {
                    affectedElements = siblingSet.slice(lastClickedIndex + 1, elIndex + 1);
                } else {
                    affectedElements = siblingSet.slice(elIndex, lastClickedIndex);
                }
                const stateChange = this.lastClicked.classList.contains('ile-selected') ? true : false;
                for (const element of affectedElements) this.toggleSelected(element, stateChange);
            } else {
                this.toggleSelected(el);
            }
        }
        else {
            this.toggleSelected(el);
        }
        this.lastClicked = el;
        this.updateToolbar();
    }

    /**
     * Sets of selectable elements are sometimes HTML siblings and sometimes not. This function
     * hides that complexity by finding the common parent between the passed element and the last
     * clicked element and generating a set of siblings from that information
     *
     * @param {HTMLElement} clicked
     * @return {JQuery<HTMLElement>}
     */
    getSelectableRange(clicked) {
        let commonParent = undefined;
        const curEls = { clicked, lastClicked: this.lastClicked };
        // Only check up to 2 levels up in the tree
        for (let i = 0; i < 2; i++) {
            if (!curEls.clicked || !curEls.lastClicked) {
                break;
            } else if (curEls.clicked === curEls.lastClicked) {
                commonParent = curEls.clicked;
                break;
            } else {
                curEls.clicked = curEls.clicked.parentElement;
                curEls.lastClicked = curEls.lastClicked.parentElement;
            }
        }
        if (commonParent) {
            return $(commonParent).find('.ile-selectable');
        } else {
            return $(clicked);
        }
    }

    /**
     * @param {HTMLElement} el
     * @param {boolean} [forceSelected]
     * If included, turns the toggle into a one way-only operation. If set to false, elements will only
     * be deselected, not selected. If set to true, elements will only be selected, but not deselected.
     */
    toggleSelected(el, forceSelected) {
        const isCurSelected = el.classList.contains('ile-selected');
        const provider = this.getProvider(el);
        const olid = provider.data(el);
        const img_src = this.getType(olid)?.image(olid);

        if (isCurSelected === forceSelected) return;
        this.setElementSelectionAttributes(el, !isCurSelected);
        if (isCurSelected) {
            this.removeSelectedItem(olid);
            const img_el = $('#ile-drag-status .images img').toArray().find(el => el.src === img_src);
            $(img_el).remove();
        } else {
            this.addSelectedItem(olid);
            this.ile.$statusImages.append(`<li><img title="${olid}" src="${img_src}"/></li>`);
        }

    }

    setElementSelectionAttributes(el, selected) {
        el.classList.toggle('ile-selected', selected);
        el.draggable = selected;
        if (selected) {
            el.addEventListener('dragstart', this.dragStart);
            el.addEventListener('dragend', this.dragEnd);
        } else {
            el.removeEventListener('dragstart', this.dragStart);
            el.removeEventListener('dragend', this.dragEnd);
        }
    }

    updateToolbar() {
        const statusParts = [];
        this.ile.$actions.empty();
        this.ile.$selectionActions.empty();
        this.ile.bulkTagger.hideTaggingMenu()
        SelectionManager.TYPES.forEach(type => {
            const count = this.selectedItems[type.singular].length;
            if (count) statusParts.push(`${count} ${count === 1 ? type.singular : type.plural}`);
        });

        if (statusParts.length) {
            this.ile.setStatusText(`${statusParts.join(', ')} selected`);
            this.ile.$selectionActions.append($('<a>Clear Selections</a>').on('click', this.clearSelectedItems));
        } else {
            this.ile.setStatusText('');
        }

        for (const action of SelectionManager.ACTIONS) {
            const items = [];
            if (action.requires_type.every(type => this.selectedItems[type].length > 0)) {
                action.applies_to_type.forEach(type => items.push(...this.selectedItems[type]));
                if (action.multiple_only ? items.length > 1 : items.length > 0)
                    if (action.href) {
                        this.ile.$actions.append($(`<a target="_blank" href="${action.href(this.getOlidsFromSelectionList(items))}">${action.name}</a>`));
                    } else if (action.onclick && action.name === 'Tag Works') {
                        this.ile.$actions.append($(`<a href="javascript:;">${action.name}</a>`).on('click', () => this.ile.updateAndShowBulkTagger(this.getOlidsFromSelectionList(items))));
                    }
            }
        }
    }

    addSelectedItem(item) {
        this.selectedItems[this.getType(item).singular].push(item);
        sessionStorage.setItem('ile-items', JSON.stringify(this.selectedItems));
    }

    removeSelectedItem(item) {
        const type = this.getType(item);
        const index = this.selectedItems[type.singular].indexOf(item);
        if (index > -1) {
            this.selectedItems[type.singular].splice(index, 1);
            sessionStorage.setItem('ile-items', JSON.stringify(this.selectedItems));
        }
    }

    getSelectedItems() {
        if (Object.keys(this.selectedItems).length === 0) {
            if (sessionStorage.getItem('ile-items')) {
                this.selectedItems = JSON.parse(sessionStorage.getItem('ile-items'));
            } else {
                SelectionManager.TYPES.forEach(type => {this.selectedItems[type.singular] = []});
            }
        }

        const items = [];
        for (const type in this.selectedItems) items.push(...this.selectedItems[type]);
        return items;
    }

    clearSelectedItems() {
        for (const type in this.selectedItems) this.selectedItems[type] = [];
        sessionStorage.setItem('ile-items', JSON.stringify(this.selectedItems));
        this.ile.reset();
    }

    /**
     * @param {DragEvent} ev
     */
    dragStart(ev) {
        const items = this.getSelectedItems();
        const from = this.curpath.match(/OL\d+[AWM]/);
        if (items.length > 1) {
            $('#ile-drag-status .images').addClass('drag-image');
            ev.dataTransfer.setDragImage($('#ile-drag-status')[0], 0, 0);
        }
        const data = {
            from: (from ? from[0] : null),
            items: this.getOlidsFromSelectionList(items)
        };
        ev.dataTransfer.setData('text/plain', JSON.stringify(data));
        ev.dataTransfer.setData('application/x.ile+json', JSON.stringify(data));
    }

    dragEnd() {
        $('#ile-drag-status .images').removeClass('drag-image');
    }

    /**
     * @param {DragEvent} ev
     */
    onDrop(ev) {
        ev.preventDefault();
        const handler = this.getHandler();
        const data = JSON.parse(ev.dataTransfer.getData('application/x.ile+json'));
        handler.ondrop(data);
        document.getElementById('test-body-mobile').classList.remove('ile-drag-over');
    }

    /**
     * @param {DragEvent} ev
     */
    allowDrop(ev) {
        if (!ev.dataTransfer?.types.includes('application/x.ile+json') || $('.ile-selected').length) return;
        const handler = this.getHandler();
        if (!handler) return;

        ev.preventDefault();
        this.ile.setStatusText(handler.message);
        document.getElementById('test-body-mobile').classList.add('ile-drag-over');
    }

    getType(olid) {
        return SelectionManager.TYPES.find(t => t.regex.test(olid));
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

    getOlidsFromSelectionList(list) {
        return list.map(item => item.split(':')[0]);
    }
}

/**
 * Cross-browser approach to clear any text selections.
 */
function clearTextSelection() {
    const selection = window.getSelection ? window.getSelection() : document.selection ? document.selection : null;
    if (!!selection) selection.empty ? selection.empty() : selection.removeAllRanges();
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

SelectionManager.TYPES = [
    {
        singular: 'work',
        plural: 'works',
        regex: /OL\d+W/,
        image: olid => {
            const imgOlid = olid.split(':').pop();
            if (imgOlid.slice(-1) === 'M')
                return `https://covers.openlibrary.org/b/olid/${imgOlid}-M.jpg?default=https://openlibrary.org/images/icons/avatar_book-lg.png`
            else
                return `https://covers.openlibrary.org/w/olid/${imgOlid}-M.jpg?default=https://openlibrary.org/images/icons/avatar_book-lg.png`
        },
    },
    {
        singular: 'edition',
        plural: 'editions',
        regex: /OL\d+M/,
        image: olid => `https://covers.openlibrary.org/b/olid/${olid}-M.jpg?default=https://openlibrary.org/images/icons/avatar_book-lg.png`,
    },
    {
        singular: 'author',
        plural: 'authors',
        regex: /OL\d+A/,
        image: olid => `https://covers.openlibrary.org/a/olid/${olid}-M.jpg?default=https://openlibrary.org/images/icons/avatar_author-lg.png`,
    }
]

/**
 * Selection Providers define what is selectable on a page. E.g. the path regex
 * determines the url to apply the selection provider to.
 */
SelectionManager.SELECTION_PROVIDERS = [
    /**
     * This selection provider makes books in search results selectable.
     */
    {
        path: /(\/authors\/OL\d+A.*|\/search)$/,
        selector: '.searchResultItem',
        type: ['work','edition'],
        /**
         * @param {HTMLElement} el
         * @return {import('../ol.js').WorkOLID}
         **/
        data: el => {
            const parts = $(el).find('.booktitle a')[0].href.match(/OL\d+[WM]/g);
            return (parts.length > 1 && parts[0] !== parts[1]) ? parts.join(':') : parts[0];
        },
    },
    /**
     * This selection provider makes editions in the editions table selectable.
     */
    {
        path: /(\/works\/OL\d+W.*|\/books\/OL\d+M.*)/,
        selector: '.book',
        type: ['edition'],
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
        type: ['author'],
        /**
         * @param {HTMLAnchorElement} el
         * @return {import('../ol.js').AuthorOLID}
         **/
        data: el => el.href.match(/OL\d+A/)[0],
    },
    /**
     * This selection provider makes authors selectable on search result pages
     */
    {
        path: /^(\/search\/authors)$/,
        selector: '.searchResultItem',
        type: ['author'],
        data: el => $(el).find('a')[0].href.match(/OL\d+A/)[0],
    },
];

/**
 * Actions get enabled when a certain selections are made.
 */
SelectionManager.ACTIONS = [
    {
        applies_to_type: ['work','edition'],
        requires_type: ['work'],
        multiple_only: false,
        name: 'Tag Works',
        onclick: true,
    },
    {
        applies_to_type: ['work','edition'],
        requires_type: ['work'],
        multiple_only: true,
        name: 'Merge Works...',
        href: olids => `/works/merge?records=${olids.join(',')}`,
    },
    /* Uncomment this when edition merging is available.
    {
        applies_to_type: ['edition'],
        requires_type: ['edition'],
        multiple_only: true,
        name: 'Merge Editions...',
        href: olids => `/works/merge?records=${olids.join(',')}`,
    },
    */
    {
        applies_to_type: ['author'],
        requires_type: ['author'],
        multiple_only: true,
        name: 'Merge Authors...',
        href: olids => `/authors/merge?records=${olids.join(',')}`,
    },
];
