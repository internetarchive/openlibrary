/**
 * Functionality for Tags form
 */
import 'jquery-ui/ui/widgets/sortable';

const pluginsTypesList = ['RelatedSubjects', 'QueryCarousel', 'ListCarousel']

function checkRequiredFields() {
    const nameInput = document.getElementById('tag_name');
    const descriptionInput = document.getElementById('tag_description');
    const tagType = document.getElementById('tag_type');
    if (!nameInput.value) {
        nameInput.focus({focusVisible: true});
        throw new Error('Name is required');
    }
    if (!descriptionInput.value) {
        descriptionInput.focus({focusVisible: true});
        throw new Error('Description is required');
    }
    if (!tagType.value) {
        tagType.focus({focusVisible: true});
        throw new Error('Tag type is required');
    }
}

export function initPluginsForm() {
    document.querySelector('.addPluginBtn').addEventListener('click', function() {
        const newRow = `
        <tr class="plugins-input-row">
            <td>
                <select id="plugins_type" class="select-tag-plugins-container">
                    <option value="">Select Plugin</option>
                    ${pluginsTypesList.map(pluginType => `<option value="${pluginType}">${pluginType}</option>`).join('')}
                </select>
            </td>
            <td><textarea id="plugin_data_input"></textarea></td>
            <td><span class="delete-plugin-btn">[X]</span></td>
            <td><span class="drag-handle">☰</span></td>
        </tr>`
        document
            .getElementById('pluginsFormRows')
            .insertAdjacentHTML('beforeEnd', newRow);
        initDeletePluginbtns(); // Reinitialize the delete-row-buttons' onclick listener
    });

    // Make the table rows draggable
    $('#pluginsFormRows').sortable({
        handle: '.drag-handle'
    });

    initDeletePluginbtns();
}

// Handle plugin deletion
function initDeletePluginbtns() {
    document.querySelectorAll('.delete-plugin-btn').forEach(function(row) {
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
            clearPluginsAndInputErrors();
            try {
                checkRequiredFields();
            } catch (e) {
                return;
            }
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
            clearPluginsAndInputErrors();
            try {
                checkRequiredFields();
            } catch (e) {
                return;
            }
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

function getPluginsData() {
    const formData = [];
    document.querySelectorAll('.plugins-input-row').forEach(function(row) {
        const pluginsType = row.querySelector('#plugins_type').value;
        const dataInput = row.querySelector('#plugin_data_input').value;

        const newPlugin = {}
        newPlugin[pluginsType] = dataInput
        const error = parseAndValidatePluginsData(newPlugin);
        if (error) {
            const errorDiv = document.getElementById('plugin_errors');
            errorDiv.classList.remove('hidden');
            errorDiv.textContent = error;
            row.classList.add('invalid-tag-plugins-error');
            throw new Error(error);
        }

        formData.push(newPlugin);
    });

    return formData;
}

function clearPluginsAndInputErrors() {
    const nameInput = document.getElementById('tag_name');
    const descriptionInput = document.getElementById('tag_description');
    const tagType = document.getElementById('tag_type');
    nameInput.focus({focusVisible: false});
    descriptionInput.focus({focusVisible: false});
    tagType.focus({focusVisible: false});
    const errorDiv = document.getElementById('plugin_errors');
    errorDiv.classList.add('hidden');
    document.querySelectorAll('.plugins-input-row').forEach(function(row) {
        row.classList.remove('invalid-tag-plugins-error');
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
        if (splitResults.length !== 2) {
            return 'Too many equal signs: Each parameter should be in the form of \'key=value\'';
        }
        const value = splitResults[1];

        if (!validInputRegex.test(pair)) {
            return `Invalid parameters: ${value}`;
        }
    }
    return null;
}
