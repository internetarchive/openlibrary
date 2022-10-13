export function initAddProviderLink(elem) {
    elem.addEventListener('click', function() {
        let index = Number(elem.dataset.index)
        elem.parentElement.insertBefore(createProviderFieldset(index), elem)
        this.dataset.index = ++index
    })
}

function createProviderFieldset(index) {
    const fieldset = document.createElement('fieldset')
    fieldset.classList.add('minor')
    const innerHtml = `<legend>Provider ${index + 1}</legend>
      ${createProviderFormElement(index, 'Book URL', 'url')}
      ${createProviderFormElement(index, 'Access Type', 'access')}
      ${createProviderFormElement(index, 'File Format', 'format')}
      ${createProviderFormElement(index, 'Provider Name', 'provider_name')}`
    fieldset.innerHTML = innerHtml
    return fieldset
}

function createProviderFormElement(index, label, type) {
    const id = `edition--providers--${index}--${type}`
    return `<div class="formElement">
      <div class="label">
          <label for="${id}">${label}</label>
      </div>
      <div class="input">
          <input name="${id}" id="${id}">
      </div>`
}
