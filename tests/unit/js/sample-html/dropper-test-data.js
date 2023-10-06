/** Part/Simplification of the .widget-add element */
export const legacyBookDropperMarkup = `
    <div class="dropper">
        <a href="javascript:;" class="dropclick dropclick-unactivated">
            <div class="arrow arrow-unactivated"></div>
        </a>
    </div>
`

export const openDropperMarkup = generateDropperMarkup(true)

export const closedDropperMarkup = generateDropperMarkup(false)

export const disabledDropperMarkup = generateDropperMarkup(false, true)

function generateDropperMarkup(isDropperOpen, isDropperDisabled = false) {
    let wrapperClasses = 'generic-dropper-wrapper'
    let arrowClasses = 'arrow'

    if (isDropperOpen) {
        wrapperClasses += ' generic-dropper-wrapper--active'
        arrowClasses += ' up'
    }

    if (isDropperDisabled) {
        wrapperClasses += ' generic-dropper--disabled'
    }

    return `
      <div class="${wrapperClasses}">
        <div class="generic-dropper">
          <div class="generic-dropper__actions">
            <div class="generic-dropper__primary">
              <button>Primary Action</button>
            </div>
            <a class="generic-dropper__dropclick" href="javascript:;">
              <div class="${arrowClasses}"></div>
            </a>
          </div>
          <div class="generic-dropper__dropdown">
            <div>Dropdown content</div>
          </div>
        </div>
      </div>
    `
}
