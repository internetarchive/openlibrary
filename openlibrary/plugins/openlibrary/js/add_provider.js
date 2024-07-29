export function initAddProviderRowLink(elem) {
  elem.addEventListener('click', function() {
    let index = Number(elem.dataset.index)
    const tbody = document.querySelector('#provider-table-body')
    tbody.appendChild(createProviderRow(index))
    if (index === 0) {
      document.querySelector('#provider-table').classList.remove('hidden')
    }
    this.dataset.index = ++index
  })
}

function createProviderRow(index) {
  const tr = document.createElement('tr')

  const innerHtml = `${createTextInputDataCell(index, 'url')}
    ${createSelectDataCell(index, 'access', accessTypeValues)}
    ${createSelectDataCell(index, 'format', formatValues)}
    ${createTextInputDataCell(index, 'provider_name')}`

  tr.innerHTML = innerHtml
  return tr
}

function createTextInputDataCell(index, type) {
  const id = `edition--providers--${index}--${type}`
  return `<td><input name="${id}" id="${id}" ${type === 'url' ? 'type="url"' : ''}></td>`
}

function createSelectDataCell(index, type, values) {
  const id = `edition--providers--${index}--${type}`
  return `<td>
    <select name="${id}" id="${id}">
    ${createSelectOptions(values)}
    </select>
    </td>`
}

const accessTypeValues = [
  {value: '', text: ''},
  {value: 'read', text: 'Read'},
  {value: 'listen', text: 'Listen'},
  {value: 'buy', text: 'Buy'},
  {value: 'borrow', text: 'Borrow'},
  {value: 'preview', text: 'Preview'}
]

const formatValues = [
  {value: '', text: ''},
  {value: 'web', text: 'Web'},
  {value: 'epub', text: 'ePub'},
  {value: 'pdf', text: 'PDF'}
]
function createSelectOptions(values) {
  let html = ''
  for (const value of values) {
    html += `<option value="${value.value}">${value.text}</option>\n`
  }
  return html
}
