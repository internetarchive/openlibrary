import $ from 'jquery';
import { confirmFromTemplate } from '../confirm-template';
/**
 * Defines functions used in the 'lists' and 'view_body' templates for Lists.
 * @module lists/ListViewBody
 */

/**
 * Adds the delete list link HTML to individual lists (i.e. on My Lists page) where the 'deleteList' class appears (from lists.html template)
 */
const itemsWithDeleteList = $('.deleteList .resultTitle');
if (itemsWithDeleteList.length) {
    const deleteListLink = $('.listDelete--myLists');
    itemsWithDeleteList.each(function() {
        $(deleteListLink).clone().prependTo(this).removeClass('hidden');
    });

    // Clean up and remove placeholder element
    $('.listDelete--myLists.hidden').remove();
}

/**
 * Adds the delete seed link HTML to individual items where the 'deleteSeed' class appears (from lists.html template)
 */
const itemsWithDeleteSeed = $('.deleteSeed .resultTitle');
if (itemsWithDeleteSeed.length) {
    const deleteSeedLink = $('.seedDelete--myLists');
    itemsWithDeleteSeed.each(function() {
        $(deleteSeedLink).clone().prependTo(this).removeClass('hidden');
    });

    // Clean up and remove placeholder element
    $('.seedDelete--myLists.hidden').remove();
}

/**
 * Makes a POST to a `.json` endpoint to remove a seed item from a list.
 * @param {string} list_key - path to list, ex: /people/openlibrary/lists/OL1L
 * @param {string} seed - path to seed book being removed, ex: /books/OL23269118M
 * @param {function} success - click function
 */
function remove_seed(list_key, seed, success) {
    if (seed[0] === '/') {
        seed = {key: seed};
    }

    $.ajax({
        type: 'POST',
        url: `${list_key}/seeds.json`,
        contentType: 'application/json',
        data: JSON.stringify({
            remove: [seed]
        }),
        dataType: 'json',

        beforeSend: function(xhr) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
        },
        success: success
    });
}

/**
 * @returns {number} count of number of seed books in a list
 */
function get_seed_count() {
    return $('ul#listResults').children().length;
}

// Add listeners to each .listDelete link element
// Sometimes .listDelete is dynamically added to the DOM, so we'll add the listener to a parent element
$('#listResults').on('click', '.listDelete a', async function() {
    const listKey = $(this).closest('[data-list-key]').data('list-key');

    if (get_seed_count() > 1 && !$(this).parent().hasClass('listDelete--myLists')) {
        const seedKey = $(this).closest('[data-seed-key]').data('seed-key');
        const template = document.getElementById('remove-seed-dialog');
        if (template && await confirmFromTemplate(template)) {
            remove_seed(listKey, seedKey, function() {
                $(`[data-seed-key='${seedKey}']`).remove();
                // update seed count
                $('#list-items-count').load(`${location.href} #list-items-count`);

                // TODO: update edition count
            });
        }
    } else {
        const template = document.getElementById('delete-list-dialog');
        if (template && await confirmFromTemplate(template)) {
            $.post(`${listKey}/delete.json`, function() {
                window.location.reload();
            });
        }
    }
});
