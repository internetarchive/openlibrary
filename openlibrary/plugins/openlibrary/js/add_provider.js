import { _ } from './i18n.js';

export function initAddProviderRowLink(elem) {
    elem.addEventListener('click', function () {
        let index = Number(elem.dataset.index);
        const tbody = document.querySelector('#provider-table-body');
        tbody.appendChild(createProviderRow(index));
        if (index === 0) {
            document.querySelector('#provider-table').classList.remove('hidden');
        }
        this.dataset.index = ++index;
    });
}

function createProviderRow(index) {
    const tr = document.createElement('tr');

    const innerHtml = `${createTextInputDataCell(index, 'url')}
    ${createSelectDataCell(index, 'access', accessTypeValues)}
    ${createSelectDataCell(index, 'format', formatValues)}
    ${createTextInputDataCell(index, 'provider_name')}`;

    tr.innerHTML = innerHtml;
    return tr;
}

function createTextInputDataCell(index, type) {
    const id = `edition--providers--${index}--${type}`;
    return `<td><input name="${id}" id="${id}" ${type === 'url' ? 'type="url"' : ''}></td>`;
}

function createSelectDataCell(index, type, values) {
    const id = `edition--providers--${index}--${type}`;
    return `<td>
    <select name="${id}" id="${id}">
    ${createSelectOptions(values)}
    </select>
    </td>`;
}

const accessTypeValues = [
    { value: '', text: '' },
    { value: 'read', text: _('Read') },
    { value: 'listen', text: _('Listen') },
    { value: 'buy', text: _('Buy') },
    { value: 'borrow', text: _('Borrow') },
    { value: 'preview', text: _('Preview') }
];

const formatValues = [
    { value: '', text: '' },
    { value: 'web', text: _('Web') },
    { value: 'epub', text: _('ePub') },
    { value: 'pdf', text: _('PDF') }
];
function createSelectOptions(values) {
    let html = '';
    for (const value of values) {
        html += `<option value="${value.value}">${value.text}</option>\n`;
    }
    return html;
}
