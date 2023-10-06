// removeChildren() test data:

// Single element, no children
export const childlessElem = '<div class="remove-tests"></div>'

// Single element, multiple children
export const multiChildElem = `<div class="remove-tests">
  <div>Child one</div>
  <div>Child two</div>
</div>`

// Single element, child with children
export const elemWithDescendants = `<div class="remove-tests">
  <div>
    <div>Ancestor</div>
  </div>
</div>`
