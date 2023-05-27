/**
 * Functionality for Tags form
 */
import 'jquery-ui/ui/widgets/sortable';

export function initPluginsForm() {
    document.getElementById('addPluginBtn').addEventListener('click', function() {
        const newRow =
    '<tr class="plugins-input-row">' +
    '<td>' +
    '<select id="plugins_type">' +
    '<option value="">Select Plugin</option>' +
    '<option value="QueryCarousel">QueryCarousel</option>' +
    '<option value="ListCarousel">ListCarousel</option>' +
    '</select>' +
    '</td>' +
    '<td><textarea id="data_input" cols="55" rows="5" tabindex="0"></textarea></td>' +
    '<td><span class="drag-handle">☰</span></td>' +
    '<td><button type="button" class="deletePluginBtn">[X]</button></td>' +
    '</tr>';
        document
            .getElementById('pluginsFormRows')
            .insertAdjacentHTML('beforeEnd', newRow);
        initDeletePluginBtns(); // Reinitialize the delete-row-buttons' onclick listener
    });

    // Make the table rows draggable
    $('#pluginsFormRows').sortable({
        handle: '.drag-handle'
    });

    initDeletePluginBtns();
}

// Handle plugin deletion
function initDeletePluginBtns() {
    document.querySelectorAll('.deletePluginBtn').forEach(function(row) {
        row.addEventListener('click', function() {
            row.closest('.plugins-input-row').remove();
        });
    });
}

export function initAddTagForm() {
    document
        .getElementById('addtag')
        .addEventListener('submit', function(e) {
            e.preventDefault();
            const pluginsData = getPluginsData();
            const pluginsInput = document.getElementById('tag_plugins');
            pluginsInput.value = JSON.stringify(pluginsData);
            // Submit the form
            this.submit();
        });
}

export function initEditTagForm() {
    document
        .getElementById('edittag')
        .addEventListener('submit', function(e) {
            e.preventDefault();
            const pluginsData = getPluginsData();
            const pluginsInput = document.getElementById('tag_plugins');
            pluginsInput.value = JSON.stringify(pluginsData);
            // Submit the form
            this.submit();
        });
}

function getPluginsData() {
    const formData = [];
    document.querySelectorAll('.plugins-input-row').forEach(function(row) {
        const pluginsType = row.querySelector('#plugins_type').value;
        const dataInput = row.querySelector('#data_input').value;

        const newPlugin = {}
        newPlugin[pluginsType] = dataInput

        formData.push(newPlugin);
    });

    return formData;
}
