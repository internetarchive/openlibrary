import { LitElement, html, css } from 'lit';

/**
 * @element ol-star-rating
 *
 * @prop {number} value - Current rating value (0-5, supports decimals) (default: 0)
 * @prop {string} size - Star size: 'small', 'medium', 'large' (default: 'medium')
 * @prop {boolean} readonly - Read-only mode, no interactions (default: false)
 * @prop {string} clearButtonLabel - Label for the clear button (default: 'Clear my rating')
 * @prop {string} ratingText - Text to display next to stars (e.g., "4.2 (1,234 ratings)") - shown automatically when set
 *
 * @fires change - Emitted when rating value changes with detail: { value }
 *
 * @example
 * <ol-star-rating value="3" size="medium"></ol-star-rating>
 * <ol-star-rating value="4" readonly></ol-star-rating>
 * <ol-star-rating value="4.5" readonly rating-text="4.5 (123 ratings)"></ol-star-rating>
 * <ol-star-rating value="3" clear-button-label="Borrar mi calificación"></ol-star-rating>
 */
export class OlStarRating extends LitElement {
    static properties = {
        value: { type: Number, reflect: true },
        size: { type: String, reflect: true },
        readonly: { type: Boolean, reflect: true },
        clearButtonLabel: { type: String, reflect: true, attribute: 'clear-button-label' },
        ratingText: { type: String, reflect: true, attribute: 'rating-text' },
        _hoverValue: { type: Number, state: true },
        _focusedIndex: { type: Number, state: true }
    };

    static styles = css`
    :host {
      display: inline-block;

      /* Temporarily hardcoding CSS values in component file for testing. */
      --spacing-inline: 8px;
      --spacing-inline-sm: 0;
      --radius-button: 4px;
      --focus-ring-width: 2px;
      --color-border-focused: #2e7bcf;
      --color-text: #333;
      --star-color-fill: #ffd400;
      --star-color-empty: #ccc  ;
    }

    .star-rating-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--spacing-inline);
    }

    :host([size="small"]) .star-rating-container {
      gap: var(--spacing-inline-sm);
    }

    .stars-wrapper {
      display: inline-flex;
      align-items: center;
      position: relative;
      gap: 2px;
    }

    .stars-and-text {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .rating-text {
      color: var(--color-text);
      font-size: 0.875rem;
      line-height: 1;
      white-space: nowrap;
    }

    .star-button {
      background: none;
      border: none;
      padding: 0;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: var(--radius-button);
    }

    .star-button:focus-visible {
      outline: var(--focus-ring-width) solid var(--color-border-focused);
      outline-offset: 2px;
    }

    :host([readonly]) .star-button {
      cursor: default;
    }

    /* Star sizes */
    .star-button.small svg {
      width: 16px;
      height: 16px;
    }

    .star-button.medium svg {
      width: 24px;
      height: 24px;
    }

    .star-button.large svg {
      width: 32px;
      height: 32px;
    }

    /* Star colors for interactive mode (not readonly) */
    .star-button svg {
      color: var(--star-color-empty);
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
    }

    .star-button.filled svg {
      color: var(--star-color-fill);
      fill: var(--star-color-fill);
    }

    /* Half-star rendering */
    .star-button.half {
      position: relative;
    }

    .star-button.half svg {
      color: var(--star-color-empty);
      fill: var(--star-color-empty);
    }

    .star-button.half .star-half-overlay {
      position: absolute;
      top: 0;
      left: 0;
      width: 50%;
      height: 100%;
      overflow: hidden;
    }

    .star-button.half .star-half-overlay svg {
      color: var(--star-color-fill);
      fill: var(--star-color-fill);
      stroke: var(--star-color-fill);
    }

    /* Star colors for readonly mode - all stars visible */
    :host([readonly]) .star-button svg {
      color: var(--star-color-empty);
      fill: var(--star-color-empty);
      stroke: var(--star-color-empty);
      stroke-width: 2;
    }

    :host([readonly]) .star-button.filled svg {
      color: var(--star-color-fill);
      fill: var(--star-color-fill);
      stroke: var(--star-color-fill);
    }

    :host([readonly]) .star-button.half svg {
      color: var(--star-color-empty);
      fill: var(--star-color-empty);
      stroke: var(--star-color-empty);
    }

    :host([readonly]) .star-button.half .star-half-overlay svg {
      color: var(--star-color-fill);
      fill: var(--star-color-fill);
      stroke: var(--star-color-fill);
    }

    /* Clear button styles */
    .clear-button {
      background-color: #fff;
      color: var(--color-text);
      border: 1px solid #ccc;
      border-radius: var(--radius-button);
      cursor: pointer;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25em 0.75em;
      text-align: center;
      white-space: nowrap;
      box-sizing: border-box;
      align-self: center;
    }

    .clear-button:focus-visible {
      outline: var(--focus-ring-width) solid var(--color-border-focused);
    }
  `;

    constructor() {
        super();
        this.value = 0;
        this.size = 'medium';
        this.readonly = false;
        this.clearButtonLabel = 'Clear my rating';
        this.ratingText = '';
        this._hoverValue = null;
        this._focusedIndex = null;
        this._totalStars = 5;
    }

    /**
     * Handle star click
     */
    _handleStarClick(index) {
        if (this.readonly) return;

        const newValue = index + 1;
        this.value = newValue;

        // Dispatch change event
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: newValue },
            bubbles: true,
            composed: true
        }));
    }

    /**
     * Handle star hover
     */
    _handleStarHover(index) {
        if (this.readonly) return;
        this._hoverValue = index + 1;
    }

    /**
     * Handle mouse leave from stars wrapper
     */
    _handleMouseLeave() {
        if (this.readonly) return;
        this._hoverValue = null;
    }

    /**
     * Handle keyboard navigation
     */
    _handleKeyDown(event, index) {
        if (this.readonly) return;

        let newIndex = index;

        switch (event.key) {
        case 'ArrowRight':
            event.preventDefault();
            newIndex = Math.min(this._totalStars - 1, index + 1);
            this._focusToStar(newIndex);
            break;
        case 'ArrowLeft':
            event.preventDefault();
            newIndex = Math.max(0, index - 1);
            this._focusToStar(newIndex);
            break;
        case 'Enter':
        case ' ':
            event.preventDefault();
            this._handleStarClick(index);
            break;
        case 'Home':
            event.preventDefault();
            this._focusToStar(0);
            break;
        case 'End':
            event.preventDefault();
            this._focusToStar(this._totalStars - 1);
            break;
        }
    }

    /**
     * Focus on a specific star by index
     */
    _focusToStar(index) {
        this._focusedIndex = index;
        this.updateComplete.then(() => {
            const stars = this.shadowRoot.querySelectorAll('.star-button');
            if (stars[index]) {
                stars[index].focus();
            }
        });
    }

    /**
     * Handle star focus
     */
    _handleStarFocus(index) {
        this._focusedIndex = index;
    }

    /**
     * Handle star blur
     */
    _handleStarBlur() {
        // Small delay to check if focus moved to another star
        setTimeout(() => {
            const activeElement = this.shadowRoot.activeElement;
            if (!activeElement || !activeElement.classList.contains('star-button')) {
                this._focusedIndex = null;
            }
        }, 0);
    }

    /**
     * Handle clear button click
     */
    _handleClear() {
        if (this.readonly) return;

        this.value = 0;

        // Dispatch change event
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: 0 },
            bubbles: true,
            composed: true
        }));
    }

    /**
     * Get star fill state
     * @param {number} index - Star index (0-based)
     * @returns {string} 'full', 'half', or 'empty'
     */
    _getStarState(index) {
        const displayValue = this._hoverValue !== null ? this._hoverValue : this.value;

        // For interactive mode, always use whole numbers
        if (!this.readonly) {
            return index < displayValue ? 'full' : 'empty';
        }

        // For readonly mode with decimals, support half stars
        const starThreshold = index + 1;
        const previousThreshold = index;

        if (displayValue >= starThreshold) {
            return 'full';
        } else if (displayValue > previousThreshold && displayValue >= previousThreshold + 0.5) {
            // Show half star if value is at least 0.5 into this star
            return 'half';
        }

        return 'empty';
    }

    /**
     * Render a star SVG
     */
    _renderStarSVG() {
        return html`
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
      >
        <path
          d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"
        />
      </svg>
    `;
    }

    /**
     * Render a star icon
     */
    _renderStar(index) {
        const starState = this._getStarState(index);
        const classes = `star-button ${this.size} ${starState === 'full' ? 'filled' : ''} ${starState === 'half' ? 'half' : ''}`;

        // Determine tab index: first star is always tabbable, or the star matching current value
        let tabIndex = -1;
        if (index === 0 && this.value === 0) {
            tabIndex = 0;
        } else if (index === Math.floor(this.value) - 1 && this.value > 0) {
            tabIndex = 0;
        }

        return html`
      <button
        class=${classes}
        type="button"
        aria-label="Rate ${index + 1} out of ${this._totalStars} stars"
        tabindex=${this.readonly ? -1 : tabIndex}
        @click=${() => this._handleStarClick(index)}
        @mouseenter=${() => this._handleStarHover(index)}
        @keydown=${(e) => this._handleKeyDown(e, index)}
        @focus=${() => this._handleStarFocus(index)}
        @blur=${() => this._handleStarBlur()}
      >
        ${this._renderStarSVG()}
        ${starState === 'half' ? html`
          <span class="star-half-overlay">
            ${this._renderStarSVG()}
          </span>
        ` : ''}
      </button>
    `;
    }

    render() {
        const stars = Array.from({ length: this._totalStars }, (_, index) =>
            this._renderStar(index)
        );

        const starsDisplay = html`
      <div
        class="stars-wrapper"
        @mouseleave=${this._handleMouseLeave}
        role="radiogroup"
        aria-label="Rating selection"
      >
        ${stars}
      </div>
    `;

        return html`
      <div
        class="star-rating-container"
        role="group"
        aria-label="Star rating"
      >
        ${this.ratingText ? html`
          <div class="stars-and-text">
            ${starsDisplay}
            <span class="rating-text">${this.ratingText}</span>
          </div>
        ` : starsDisplay}

        ${this.value > 0 && !this.readonly ? html`
          <button
            class="clear-button"
            type="button"
            @click=${this._handleClear}
          >
            ${this.clearButtonLabel}
          </button>
        ` : ''}
      </div>
    `;
    }
}

customElements.define('ol-star-rating', OlStarRating);

