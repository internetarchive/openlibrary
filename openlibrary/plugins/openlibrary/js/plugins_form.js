/**
 * Functionality for Tags form
 */
import 'jquery-ui/ui/widgets/sortable';

const pluginsTypesList = ['QueryCarousel', 'ListCarousel']

export function initPluginsForm() {
    document.getElementById('addPluginBtn').addEventListener('click', function() {
        const newRow =
    `${'<tr class="plugins-input-row">' +
    '<td>' +
    '<select id="plugins_type" style="margin: 5px; max-width: 130px;">' +
    '<option value="">Select Plugin</option>'}${
        pluginsTypesList.map(function(pluginType) {
            return `<option value="${pluginType}">${pluginType}</option>`;
        }).join('')
    }</select>` +
    '</td>' +
    '<td><textarea id="data_input" cols="55" rows="5" tabindex="0"></textarea></td>' +
    '<td><span class="deletePluginBtn" style="color: red; cursor: pointer; margin-left: 10px;">[X]</span></td>' +
    '<td><span class="drag-handle" style="margin: 10px; font-size: 20px; cursor: move;">☰</span></td>' +
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
            clearPluginsError();
            let pluginsData = [];
            try {
                pluginsData = getPluginsData();
            } catch (e) {
                return;
            }
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
            clearPluginsError();
            let pluginsData = [];
            try {
                pluginsData = getPluginsData();
            } catch (e) {
                console.log(e);
                return;
            }
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
        const error = parseAndValidatePluginsData(newPlugin);
        if (error) {
            const errorDiv = document.getElementById('plugin_errors');
            errorDiv.classList.remove('hidden');
            errorDiv.textContent = error;
            row.setAttribute('style', 'border: 1px solid red;');
            throw new Error(error);
        }

        formData.push(newPlugin);
    });

    return formData;
}

function clearPluginsError() {
    const errorDiv = document.getElementById('plugin_errors');
    errorDiv.classList.add('hidden');
    document.querySelectorAll('.plugins-input-row').forEach(function(row) {
        row.removeAttribute('style');
    });
}

function parseAndValidatePluginsData(plugin) {
    const validInputRegex = /^[\w\s]+=(?:'[^']*'|"[^"]*"|\w+)$/;
    const pluginType = Object.keys(plugin)[0];
    const pluginData = plugin[pluginType];
    if (!pluginType) {
        return 'Plugin type is required';
    }
    if (!pluginsTypesList.includes(pluginType)) {
        return `Invalid plugin type: ${pluginType}`;
    }
    if (!pluginData) {
        return 'Plugin parameters are required';
    }
    const keyValuePairs = pluginData.split(', ');
    for (const pair of keyValuePairs) {
        if (!pair.includes('=')) {
            return 'Missing equal sign: Each parameter should be in the form of \'key=value\'';
        }
        const splitResults = pair.split('=');
        if (splitResults.length != 2) {
            return 'Too many equal signs: Each parameter should be in the form of \'key=value\'';
        }
        const value = splitResults[1];

        if (!validInputRegex.test(pair)) {
            return `Invalid parameters: ${value}`;
        }
    }
    return null;
}
