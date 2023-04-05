/**
 * Defines functions used in 'view_body' template for Lists.
 * @module lists/ListViewBody
 */

/**
 * Makes a POST to a `.json` endpoint to remove a seed item from a list.
 * @param {string} list_key - path to list, ex: /people/openlibrary/lists/OL1L
 * @param {string} seed - path to seed book being removed, ex: /books/OL23269118M
 * @param {function} success - click function
 */
function remove_seed(list_key, seed, success) {
    if (seed[0] == "/") {
        seed = {"key": seed}
    }

    $.ajax({
        type: "POST",
        url: list_key + "/seeds.json",
        contentType: "application/json",
        data: JSON.stringify({
            "remove": [seed]
        }),
        dataType: "json",

        beforeSend: function(xhr) {
            xhr.setRequestHeader("Content-Type", "application/json");
            xhr.setRequestHeader("Accept", "application/json");
        },
        success: success
    });
}

/**
 * @returns {number} count of number of seed books in a list
 */
function get_seed_count() {
    return $("ul#listResults").children().length;
}

/**
 * Get the i18n 'cancel' text label passed from data attribute; this is set in the view_body.html template file
 * @returns {string} i18n cancel text
 */
const getCancelButtonLabelText = () => {
    return $('.listDelete a').data('cancel-text');
};

/**
 * Get the i18n 'confirm' text label passed from data attribute; this is set in the view_body.html template file
 * @returns {string} i18n confirmation text
 */
const getConfirmButtonLabelText = () => {
    return $('.listDelete a').data('confirm-text');
};

// Add listeners to each .listDelete link element
$(".listDelete a").on('click', function() {
    if (get_seed_count() > 1) {
        $("#remove-seed-dialog")
            .data("seed-key", $(this).closest("[data-seed-key]").data('seed-key'))
            .data("list-key", $(this).closest("[data-list-key]").data('list-key'))
            .dialog("open");
        $("#remove-seed-dialog").removeClass('hidden');
    }
    else {
        $("#delete-list-dialog")
            .data("list-key", $(this).closest("[data-list-key]").data('list-key'))
            .dialog("open");
        $("#delete-list-dialog").removeClass('hidden');
    }
});

// Set up 'Remove Seed' dialog; force user to confirm the destructive action of removing a seed
$("#remove-seed-dialog").dialog({
    autoOpen: false,
    width: 400,
    modal: true,
    resizable: false,
    buttons: {
        "ConfirmRemoveSeed": {
            text: getConfirmButtonLabelText(),
            id: "remove-seed-dialog--confirm",
            click: function() {
                var list_key = $(this).data("list-key");
                var seed_key = $(this).data("seed-key");

                var _this = this;

                remove_seed(list_key, seed_key, function() {
                    $(`[data-seed-key="${seed_key}"]`).remove();
                    // update seed count
                    $("#list-items-count").load(location.href + " #list-items-count");

                    // TODO: update edition count

                    $(_this).dialog("close");
                    $("#remove-seed-dialog").addClass('hidden');
                });
            }
        },
        "CancelRemoveSeed": {
            text: getCancelButtonLabelText(),
            id: "remove-seed-dialog--cancel",
            click: function() {
                $(this).dialog("close");
                $("#remove-seed-dialog").addClass('hidden');
            }
        }
    }
});

// Set up 'Delete List' dialog; force user to confirm the destructive action of deleting a list
$("#delete-list-dialog").dialog({
    autoOpen: false,
    width: 400,
    modal: true,
    resizable: false,
    buttons: {
        "ConfirmDeleteList": {
            text: getConfirmButtonLabelText(),
            id: "delete-list-dialog--confirm",
            click: function() {
                var list_key = $(this).data("list-key");
                var _this = this;

                $.post(list_key + "/delete.json", function() {
                    $(_this).dialog("close");
                    window.location.reload();
                });
            }
        },
        "CancelDeleteList": {
            text: getCancelButtonLabelText(),
            id: "delete-list-dialog--cancel",
            click: function() {
                $(this).dialog("close");
            }
        }
    }
});
