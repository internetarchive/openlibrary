/** Part/Simplification of the .widget-add element */
export const legacyBookDropperMarkup = `
    <div class="dropper">
        <a href="javascript:;" class="dropclick dropclick-unactivated">
            <div class="arrow arrow-unactivated"></div>
        </a>
    </div>
`;

export const openDropperMarkup = generateDropperMarkup(true);

export const closedDropperMarkup = generateDropperMarkup(false);

export const disabledDropperMarkup = generateDropperMarkup(false, true);

/**
 * Stand-in for `<ol-popover>`: the dropper only touches `open`, the trigger
 * click, and the open/close events. Registering it here keeps the dropper
 * tests off Lit while still exercising the real contract.
 *
 * Call once per test file, before building any dropper markup.
 *
 * @returns {void}
 */
export function defineStubPopover() {
    if (customElements.get('ol-popover')) return;

    customElements.define('ol-popover', class extends HTMLElement {
        connectedCallback() {
            if (this._wired) return;
            this._wired = true;
            this.addEventListener('click', (event) => {
                if (event.target.closest('[slot="trigger"]')) {
                    this.open = !this.open;
                }
            });
        }

        get open() {
            return this.hasAttribute('open');
        }

        set open(value) {
            const next = Boolean(value);
            if (next === this.open) return;
            this.toggleAttribute('open', next);
            this.dispatchEvent(new CustomEvent(next ? 'ol-popover-open' : 'ol-popover-close', {
                bubbles: true,
                composed: true,
                detail: next ? { placement: 'bottom-end' } : { reason: 'trigger' },
            }));
        }
    });
}

function generateDropperMarkup(isDropperOpen, isDropperDisabled = false) {
    let wrapperClasses = 'generic-dropper-wrapper';

    if (isDropperDisabled) {
        wrapperClasses += ' generic-dropper--disabled';
    }

    return `
      <div class="${wrapperClasses}">
        <div class="generic-dropper">
          <div class="generic-dropper__actions">
            <div class="generic-dropper__primary">
              <button>Primary Action</button>
            </div>
            <ol-popover class="generic-dropper__popover"${isDropperOpen ? ' open' : ''} aria-label="More options">
              <button type="button" slot="trigger" class="generic-dropper__dropclick" aria-label="More options">
                <span class="arrow" aria-hidden="true"></span>
              </button>
              <div class="generic-dropper__dropdown">
                <div>Dropdown content</div>
              </div>
            </ol-popover>
          </div>
        </div>
      </div>
    `;
}
