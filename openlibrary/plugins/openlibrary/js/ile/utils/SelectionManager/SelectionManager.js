import $ from 'jquery';
import { move_to_work, move_to_author } from '../ol.js';
import './SelectionManager.less';

const SelectionManager = {};
export default SelectionManager;

SelectionManager.inited = false;
SelectionManager.DRAG_TOOLBAR_HTML = `
<div id="dc-drag-toolbar">
    <div style="flex: 1">
        <div id="dc-drag-status">
            <div class="text"></div>
            <div class="images"></div>
        </div>
    </div>
    <div id="dc-drag-actions"></div>
</div>`.trim();


SelectionManager.init = function () {
    SelectionManager.inited = true;
    const providers = SelectionManager.getPossibleProviders();
    const providerSelectors = providers.map(p => p.selector);
    $(providerSelectors.join(', '))
        .addClass('dc-selectable')
        .on('click', SelectionManager.toggleSelected);
    for (let provider of providers) {
        if (provider.addHandle) {
            for (let el of $(provider.selector).toArray()) {
                const handle = $('<span class="dc-select-handle">&bull;</span>');
                handle[0].addEventListener('click', ev => ev.preventDefault(), { capture: true });
                $(el).prepend(handle);
            }
        }
    }

    $(document.body).append($(SelectionManager.DRAG_TOOLBAR_HTML));
    document.body.addEventListener('drop', SelectionManager.onDrop);
    document.body.addEventListener('dragover', SelectionManager.allowDrop);
};

/**
 * @param {MouseEvent} clickEvent
 */
SelectionManager.toggleSelected = function (clickEvent) {
    const el = clickEvent.currentTarget;
    el.classList.toggle('dc-selected');
    const selected = el.classList.contains('dc-selected');
    el.draggable = selected;
    const provider = SelectionManager.getProvider(el);
    // FIXME: this is a bug if we support selecting multiple types
    const count = $('.dc-selected').length;
    SelectionManager.setStatusText(`${count} ${count == 1 ? provider.singular : provider.plural} selected`);
    $('#dc-drag-actions').empty();
    const img_src = provider.image(el);

    if (selected) {
        el.addEventListener('dragstart', SelectionManager.dragStart);
        const factor = -sigmoid($('#dc-drag-status .images img').length) + 1 + 0.5;
        $('#dc-drag-status .images').append(`<img src="${img_src}" style="padding: ${(1 - factor) * 5}px 0; width: ${(factor ** 3) * 100}%"/>`);

        const actions = SelectionManager.ACTIONS.filter(a => {
            return a.applies_to_type == provider.singular &&
        (a.multiple_only ? count > 1 : count > 0);
        });
        const items = SelectionManager.getSelectedItems();
        for (let action of actions) {
            $('#dc-drag-actions').append($(`<a target="_blank" href="${action.href(items)}">${action.name}</a>`));
        }
    } else {
        el.removeEventListener('dragstart', SelectionManager.dragStart);
        const img_el = $('#dc-drag-status .images img').toArray().find(el => el.src == img_src);
        $(img_el).remove();
    }
};

SelectionManager.dragStart = function (dragEvent) {
    const selected = $('.dc-selected').toArray();
    if (selected.length > 1) {
        dragEvent.dataTransfer.setDragImage($('#dc-drag-status')[0], 0, 0);
    }
    const data = {
        from: location.pathname.match(/OL\d+[AWM]/)[0],
        items: SelectionManager.getSelectedItems()
    };
    dragEvent.dataTransfer.setData('text', JSON.stringify(data));
};

SelectionManager.getSelectedItems = function () {
    return $('.dc-selected').toArray().map(el => SelectionManager.getProvider(el).data(el));
};

SelectionManager.onDrop = function (ev) {
    ev.preventDefault();
    const handler = SelectionManager.getHandler();
    const data = JSON.parse(ev.dataTransfer.getData('text'));
    handler.ondrop(data);
}

SelectionManager.allowDrop = function (ev) {
    const handler = SelectionManager.getHandler();
    if ($('.dc-selected').length || !handler) return;

    ev.preventDefault();
    SelectionManager.setStatusText(handler.message);
};

SelectionManager.getHandler = function () {
    return SelectionManager.DROP_HANDLERS.find(h => h.path.test(location.pathname));
};

SelectionManager.getPossibleProviders = function () {
    return SelectionManager.SELECTION_PROVIDERS.filter(p => p.path.test(location.pathname));
};

/**
 * @param {HTMLElement} el
 */
SelectionManager.getProvider = function (el) {
    return SelectionManager.SELECTION_PROVIDERS
        .find(p => p.path.test(location.pathname) && el.matches(p.selector));
}

SelectionManager.setStatusText = function (text) {
    $('#dc-drag-status .text').text(text);
}

SelectionManager.DROP_HANDLERS = [
    {
        path: /\/authors\/OL\d+A.*/,
        message: 'Move to this author',
        async ondrop(data) {
            // eslint-disable-next-line no-console
            console.log('move', data);
            SelectionManager.setStatusText('Working...');
            try {
                await move_to_author(data.items, data.from, location.pathname.match(/OL\d+A/)[0]);
                SelectionManager.setStatusText('Completed!');
            } catch (e) {
                SelectionManager.setStatusText('Errored!');
                throw e;
            }
        }
    },
    {
        path: /\/works\/OL\d+W.*/,
        message: 'Move to this work',
        async ondrop(data) {
            // eslint-disable-next-line no-console
            console.log('move', data);
            SelectionManager.setStatusText('Working...');
            try {
                await move_to_work(data.items, data.from, location.pathname.match(/OL\d+W/)[0]);
                SelectionManager.setStatusText('Completed!');
            } catch (e) {
                SelectionManager.setStatusText('Errored!');
                throw e;
            }
        }
    },
];

SelectionManager.SELECTION_PROVIDERS = [
    {
        path: /\/authors\/OL\d+A.*/,
        selector: '.searchResultItem',
        image: el => $(el).find('.bookcover img')[0].src,
        singular: 'work',
        plural: 'works',
        /**
     * @param {HTMLElement} el
     * @return {WorkOLID}
     **/
        data: el => $(el).find('.booktitle a')[0].href.match(/OL\d+W/)[0],
    },
    {
        path: /\/search/,
        selector: '.searchResultItem',
        image: el => $(el).find('.bookcover img')[0].src,
        singular: 'work',
        plural: 'works',
        /**
     * @param {HTMLElement} el
     * @return {WorkOLID}
     **/
        data: el => $(el).find('.booktitle a')[0].href.match(/OL\d+W/)[0],
    },
    {
        path: /\/works\/OL\d+W.*/,
        selector: '.book',
        image: el => $(el).find('.cover img')[0].src,
        singular: 'edition',
        plural: 'editions',
        /**
     * @param {HTMLElement} el
     * @return {EditionOLID}
     **/
        data: el => $(el).find('.title a')[0].href.match(/OL\d+M/)[0],
    },
    {
        path: /\/works\/OL\d+W.*/,
        selector: 'a[href^="/authors/OL"]',
        addHandle: true,
        image: el => `https://covers.openlibrary.org/a/olid/${el.href.match(/OL\d+A/)[0]}-M.jpg?default=https://openlibrary.org/images/icons/avatar_author-lg.png`,
        singular: 'author',
        plural: 'authors',
        /**
     * @param {HTMLElement} el
     * @return {AuthorOLID}
     **/
        data: el => el.href.match(/OL\d+A/)[0],
    },
];

SelectionManager.ACTIONS = [
    {
        applies_to_type: 'work',
        multiple_only: true,
        name: 'Merge Works...',
        href: olids => `/works/merge?records=${olids.join(',')}`,
    },
    {
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
