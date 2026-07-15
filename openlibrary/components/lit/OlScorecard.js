import { LitElement, html, css, nothing } from 'lit';

let _idCounter = 0;

const TAB_GAUGE_SIZE = 64;
const TAB_GAUGE_STROKE_WIDTH = 6;
const TAB_GAUGE_FONT_SIZE = 'var(--font-size-headline-small, 24px)';
const COLLAPSED_GAUGE_SIZE = 28;
const COLLAPSED_GAUGE_STROKE_WIDTH = 4;

/**
 * OlScoreGauge - Circular gauge for OlScorecard: arc length and color track
 * a 0-100 percentage. Used for the collapsed badge, the Total indicator, and
 * each section tab. Internal helper, not part of the public component index.
 */
class OlScoreGauge extends LitElement {
    static properties = {
        percentage: { type: Number },
        size: { type: Number },
        strokeWidth: { type: Number, attribute: 'stroke-width' },
        fontSize: { type: String, attribute: 'font-size' },
        showPercent: { type: Boolean, attribute: 'show-percent' },
    };

    static styles = css`
        :host {
            display: inline-block;
        }

        .gauge {
            position: relative;
            border-radius: var(--border-radius-circle, 50%);
        }

        .gauge svg {
            display: block;
            transform: rotate(-90deg);
        }

        .track {
            fill: none;
            stroke-opacity: 0.1;
        }

        .arc {
            fill: none;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.3s;
        }

        .value {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: normal;
        }
    `;

    constructor() {
        super();
        this.percentage = 0;
        this.size = 64;
        this.strokeWidth = 6;
        this.fontSize = 'var(--font-size-label-medium, 12px)';
        this.showPercent = false;
    }

    /**
     * Threshold color for the current percentage, as a CSS custom-property
     * reference with a literal fallback (never a hardcoded default), so a
     * consumer can still override e.g. --scorecard-excellent from outside.
     * @returns {String}
     */
    _colorVar() {
        if (this.percentage >= 80) return 'var(--scorecard-excellent, #4caf50)';
        if (this.percentage >= 60) return 'var(--scorecard-good, #8bc34a)';
        if (this.percentage >= 40) return 'var(--scorecard-moderate, #ffc107)';
        if (this.percentage >= 20) return 'var(--scorecard-needs-work, #ff9800)';
        return 'var(--scorecard-poor, #f44336)';
    }

    /** @returns {import('lit').TemplateResult} */
    render() {
        const { size, strokeWidth, percentage, fontSize, showPercent } = this;
        const radius = (size - strokeWidth) / 2;
        const circumference = 2 * Math.PI * radius;
        const dashoffset = circumference * (1 - percentage / 100);
        const center = size / 2;
        const color = this._colorVar();

        return html`
            <div
                class="gauge"
                style="width: ${size}px; height: ${size}px; background-color: color-mix(in srgb, ${color} 18%, transparent)"
            >
                <svg viewBox="0 0 ${size} ${size}" width=${size} height=${size} aria-hidden="true">
                    <circle class="track" cx=${center} cy=${center} r=${radius} stroke-width=${strokeWidth} style="stroke: ${color}"></circle>
                    <circle
                        class="arc"
                        cx=${center}
                        cy=${center}
                        r=${radius}
                        stroke-width=${strokeWidth}
                        stroke-dasharray=${circumference}
                        stroke-dashoffset=${dashoffset}
                        style="stroke: ${color}"
                    ></circle>
                </svg>
                <span class="value" style="color: ${color}; font-size: ${fontSize}">${percentage}${showPercent ? '%' : ''}</span>
            </div>
        `;
    }
}

if (!customElements.get('ol-score-gauge')) {
    customElements.define('ol-score-gauge', OlScoreGauge);
}

/**
 * OlScorecard - A tabbed scorecard: each section is a gauge tab listing its
 * failing checks (always shown) and passing checks (collapsed by default).
 * A "Total" gauge and separator lead the tab row. Each check row expands to
 * show its description via a trailing chevron.
 *
 * Collapsed by default to a small badge (gauge, name, chevron); click it to
 * expand, click the header to collapse again.
 *
 * @element ol-scorecard
 *
 * @prop {Object} results - The scorecard data:
 *     `{ name, score, maxScore, sections: [{ name, score, maxScore, checks: [{ description, details, score, passing }] }] }`.
 *     Settable as a JSON attribute (`results='{"score":10,...}'`) or property.
 * @prop {Boolean} expanded - Whether the full tabbed UI is shown instead of the
 *     collapsed badge. Default `false`. Presence of the attribute expands it.
 * @prop {String} labelTotal - Label for the non-interactive "Total" gauge (default: "Total")
 * @prop {String} labelFailingChecks - Failing checks section heading template, use `{count}` (default: "Failing Checks ({count})")
 * @prop {String} labelPassingChecks - Passing checks section heading template, use `{count}` (default: "Passing Checks ({count})")
 * @prop {String} labelPoints - Check point-value template, use `{score}` (default: "{score} points")
 * @prop {String} labelExpand - Accessible label for the collapsed badge button, use `{name}`, `{percentage}` (default: "{name}: {percentage}%. Click to expand.")
 * @prop {String} labelCollapse - Accessible label for the header collapse button (default: "Collapse")
 * @prop {Boolean} outdated - Whether the solr record is stale relative to the database. Default `false`. Presence of the attribute shows a warning banner at the top of the expanded card; no banner is shown otherwise.
 * @prop {String} labelOutdated - Warning banner text shown when outdated (default: "This record has been edited and is not yet reflected in Solr. It should update in a minute or so.")
 *
 * @example
 * <ol-scorecard expanded results='{"name":"Edition Scorecard","score":40,"maxScore":100,"sections":[{"name":"Access","score":40,"maxScore":100,"checks":[{"description":"Has title","details":"...","score":40,"passing":true}]}]}'></ol-scorecard>
 */
export class OlScorecard extends LitElement {
    static properties = {
        results: { type: Object },
        expanded: { type: Boolean, reflect: true },
        labelTotal: { type: String, attribute: 'label-total' },
        labelFailingChecks: { type: String, attribute: 'label-failing-checks' },
        labelPassingChecks: { type: String, attribute: 'label-passing-checks' },
        labelPoints: { type: String, attribute: 'label-points' },
        labelExpand: { type: String, attribute: 'label-expand' },
        labelCollapse: { type: String, attribute: 'label-collapse' },
        outdated: { type: Boolean },
        labelOutdated: { type: String, attribute: 'label-outdated' },
        _activeSection: { type: Number, state: true },
    };

    /** Chevron icon; rotated by callers to indicate open/closed state. */
    static _chevronIcon = html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

    /** Clock icon; shown in the outdated-data warning banner. */
    static _clockIcon = html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>`;

    static styles = css`
        :host {
            display: inline-block;
            border: var(--border-card, 1px solid #ddd);
            border-radius: var(--border-radius-pill, 9999px);
            padding: 0;
        }

        :host([expanded]) {
            display: block;
            max-width: 480px;
            border-radius: var(--border-radius-card, 9px);
            padding: var(--spacing-inset-sm, 8px) var(--spacing-inset-xs, 4px);
            margin: var(--spacing-inset-md, 16px) 0;
        }

        .collapsed-toggle {
            display: inline-flex;
            align-items: center;
            gap: var(--spacing-inline-md, 8px);
            background: none;
            border: none;
            font: inherit;
            cursor: pointer;
            padding: var(--spacing-inset-xs, 4px);
            /* Room for chevron */
            padding-right: 12px;
        }

        .collapsed-toggle:focus-visible {
            outline: var(--focus-width, 2px) solid var(--color-focus-ring, #1a73e8);
            outline-offset: 2px;
        }

        .collapsed-label {
            font-size: var(--font-size-body-medium, 14px);
        }

        .collapsed-chevron {
            width: 1em;
            height: 1em;
            flex-shrink: 0;
        }

        .header {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md, 8px);
            width: 100%;
            padding: var(--spacing-inset-md, 16px);
            font-size: var(--font-size-title-medium, 16px);
            background: none;
            border: none;
            font-family: inherit;
            text-align: left;
            cursor: pointer;
        }

        .header:focus-visible {
            outline: var(--focus-width, 2px) solid var(--color-focus-ring, #1a73e8);
            outline-offset: 2px;
        }

        .header-chevron {
            width: 1.1em;
            height: 1.1em;
            flex-shrink: 0;
            transform: rotate(180deg);
        }

        .tabs {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-lg, 12px);
            padding: var(--spacing-inset-lg, 24px);
            justify-content: center;
            flex-wrap: wrap;
        }

        .tab-separator {
            align-self: stretch;
            width: var(--border-width-divider, 1px);
            background: var(--color-border-subtle, #ddd);
        }

        .tab {
            display: flex;
            flex-direction: column;
            align-items: center;
            background: none;
            border: none;
            border-radius: var(--border-radius-button, 6px);
            font: inherit;
            padding: var(--spacing-inset-sm, 8px);
        }

        .tab--total {
            cursor: default;
        }

        button.tab {
            cursor: pointer;
        }

        ol-score-gauge {
            background: var(--white, white);
            border-radius: 100px;
            box-shadow: 0 0 4px 2px var(--white, white);
        }

        button.tab:hover ol-score-gauge {
            transform: scale(1.05);
        }

        button.tab[aria-selected="true"] {
            background: var(--lightest-grey, #ededed);
        }

        button.tab[aria-selected="true"] .tab-label {
            font-weight: bold;
        }

        button.tab:focus-visible {
            outline: var(--focus-width, 2px) solid var(--color-focus-ring, #1a73e8);
            outline-offset: 2px;
        }

        .tab-label {
            margin-top: var(--spacing-stack-sm, 8px);
            font-size: var(--font-size-body-medium, 14px);
            text-align: center;
            max-width: 120px;
        }

        .tab-points {
            font-size: var(--font-size-label-small, 11px);
            color: color-mix(in srgb, currentColor 65%, transparent);
        }

        .section {
            padding: var(--spacing-inset-lg, 24px) var(--spacing-inset-xs, 4px);
        }

        .checks-group {
            margin-bottom: var(--spacing-stack-sm, 8px);
        }

        .checks-heading {
            margin: 0;
            padding: var(--spacing-inset-sm, 8px) var(--spacing-inset-md, 16px) var(--spacing-inset-xs, 4px);
            color: var(--accessible-grey, #767676);
            font-size: var(--font-size-label-medium, 12px);
            font-weight: normal;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            list-style: none;
        }

        .checks-heading::-webkit-details-marker {
            display: none;
        }

        details > .checks-heading {
            cursor: pointer;
        }

        .check {
            font-size: var(--font-size-body-medium, 14px);
            border-bottom: var(--border-divider, 1px solid #ddd);
        }

        .check:last-child {
            border-bottom: none;
        }

        .check[open] {
            border: var(--border-card, 1px solid #ddd);
            border-radius: var(--border-radius-md, 6px);
            margin: var(--spacing-stack-xs, 4px) 0;
            padding: 0 var(--spacing-inset-sm, 8px);
        }

        .check[open] + .check {
            border-top: var(--border-divider, 1px solid #ddd);
        }

        .check summary {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md, 8px);
            padding: var(--spacing-inset-sm, 8px) 0;
            cursor: pointer;
            font-weight: normal;
            list-style: none;
        }

        .check summary::-webkit-details-marker {
            display: none;
        }

        .check-points {
            white-space: nowrap;
        }

        .check-chevron {
            width: 1em;
            height: 1em;
            flex-shrink: 0;
        }

        .check[open] .check-chevron {
            transform: rotate(180deg);
        }

        .check-details {
            padding: var(--spacing-inset-sm, 8px) 0;
            font-size: var(--font-size-label-medium, 12px);
            color: color-mix(in srgb, currentColor 65%, transparent);
        }

        .outdated-banner {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md, 8px);
            margin: 0 var(--spacing-inset-md, 16px) var(--spacing-inset-md, 16px);
            padding: var(--spacing-inset-sm, 8px);
            border-radius: var(--border-radius-md, 6px);
            font-size: var(--font-size-label-medium, 12px);
            background-color: var(--scorecard-warning-bg, hsl(32deg 100% 90%));
            color: var(--scorecard-warning-text, hsl(32deg 100% 35%));
        }

        .outdated-banner-icon {
            width: 1.2em;
            height: 1.2em;
            flex-shrink: 0;
        }
    `;

    constructor() {
        super();
        this.results = null;
        this.expanded = false;
        this.labelTotal = 'Total';
        this.labelFailingChecks = 'Failing Checks ({count})';
        this.labelPassingChecks = 'Passing Checks ({count})';
        this.labelPoints = '{score} points';
        this.labelExpand = '{name}: {percentage}%. Click to expand.';
        this.labelCollapse = 'Collapse';
        this.outdated = false;
        this.labelOutdated = 'This record has been edited and is not yet reflected in Solr. It should update in a minute or so.';
        this._activeSection = 0;
        this._panelIdPrefix = `ol-scorecard-${++_idCounter}`;
    }

    /**
     * @param {String} template
     * @param {Object} values
     * @returns {String}
     */
    _interpolateLabel(template, values) {
        return template.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? '');
    }

    /**
     * @param {Number} score
     * @param {Number} maxScore
     * @returns {Number}
     */
    _percentage(score, maxScore) {
        return maxScore > 0 ? Math.round((score / maxScore) * 100) : 0;
    }

    /**
     * @param {KeyboardEvent} e
     * @param {Number} index
     * @returns {void}
     */
    _onTabKeydown(e, index) {
        const sections = this.results?.sections ?? [];
        let next = null;
        if (e.key === 'ArrowRight') next = (index + 1) % sections.length;
        else if (e.key === 'ArrowLeft') next = (index - 1 + sections.length) % sections.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = sections.length - 1;
        else return;

        e.preventDefault();
        this._activeSection = next;
        this.shadowRoot.querySelectorAll('button.tab')[next]?.focus();
    }

    /** @returns {import('lit').TemplateResult|typeof nothing} */
    render() {
        if (!this.results) return nothing;

        return this.expanded ? this._renderExpanded() : this._renderCollapsed();
    }

    /** @returns {import('lit').TemplateResult} */
    _renderCollapsed() {
        const { name, score, maxScore } = this.results;
        const percentage = this._percentage(score, maxScore);
        const ariaLabel = this._interpolateLabel(this.labelExpand, { name, percentage });

        return html`
            <button
                type="button"
                class="collapsed-toggle"
                aria-expanded="false"
                aria-label=${ariaLabel}
                @click=${() => { this.expanded = true; }}
            >
                <ol-score-gauge percentage=${percentage} size=${COLLAPSED_GAUGE_SIZE} stroke-width=${COLLAPSED_GAUGE_STROKE_WIDTH}></ol-score-gauge>
                <span class="collapsed-label" aria-hidden="true">${name}</span>
                <span class="collapsed-chevron" aria-hidden="true">${OlScorecard._chevronIcon}</span>
            </button>
        `;
    }

    /** @returns {import('lit').TemplateResult} */
    _renderExpanded() {
        const { name, score, maxScore, sections } = this.results;
        const percentage = this._percentage(score, maxScore);

        return html`
            <button
                type="button"
                class="header"
                aria-expanded="true"
                @click=${() => { this.expanded = false; }}
            >
                <span style="flex: 1">${name}</span>
                <span class="header-chevron" aria-label=${this.labelCollapse}>${OlScorecard._chevronIcon}</span>
            </button>

            ${this._renderOutdatedBanner()}

            <div class="tabs" role="tablist">
                <div class="tab tab--total" role="presentation">
                    <ol-score-gauge percentage=${percentage} size=${TAB_GAUGE_SIZE} stroke-width=${TAB_GAUGE_STROKE_WIDTH} font-size=${TAB_GAUGE_FONT_SIZE} show-percent></ol-score-gauge>
                    <span class="tab-label">${this.labelTotal}</span>
                    <span class="tab-points">${score}/${maxScore}</span>
                </div>

                <div class="tab-separator" role="presentation"></div>

                ${sections.map((section, i) => {
        const sectionPct = this._percentage(section.score, section.maxScore);
        const isActive = i === this._activeSection;
        const panelId = `${this._panelIdPrefix}-panel-${i}`;
        const tabId = `${this._panelIdPrefix}-tab-${i}`;
        return html`
                        <button
                            type="button"
                            class="tab"
                            id=${tabId}
                            role="tab"
                            aria-selected=${isActive}
                            aria-controls=${panelId}
                            tabindex=${isActive ? '0' : '-1'}
                            @click=${() => { this._activeSection = i; }}
                            @keydown=${(e) => this._onTabKeydown(e, i)}
                        >
                            <ol-score-gauge percentage=${sectionPct} size=${TAB_GAUGE_SIZE} stroke-width=${TAB_GAUGE_STROKE_WIDTH} font-size=${TAB_GAUGE_FONT_SIZE} show-percent></ol-score-gauge>
                            <span class="tab-label">${section.name}</span>
                            <span class="tab-points">${section.score}/${section.maxScore}</span>
                        </button>
                    `;
    })}
            </div>

            ${sections.map((section, i) => this._renderSectionPanel(section, i))}
        `;
    }

    /** @returns {import('lit').TemplateResult|typeof nothing} */
    _renderOutdatedBanner() {
        if (!this.outdated) return nothing;

        return html`
            <div class="outdated-banner">
                <span class="outdated-banner-icon">${OlScorecard._clockIcon}</span>
                <span>${this.labelOutdated}</span>
            </div>
        `;
    }

    /**
     * @param {Object} section
     * @param {Number} index
     * @returns {import('lit').TemplateResult}
     */
    _renderSectionPanel(section, index) {
        const isActive = index === this._activeSection;
        const panelId = `${this._panelIdPrefix}-panel-${index}`;
        const tabId = `${this._panelIdPrefix}-tab-${index}`;

        const failingChecks = section.checks.filter(c => !c.passing).sort((a, b) => b.score - a.score);
        const passingChecks = section.checks.filter(c => c.passing).sort((a, b) => b.score - a.score);

        return html`
            <div
                class="section"
                id=${panelId}
                role="tabpanel"
                aria-labelledby=${tabId}
                ?hidden=${!isActive}
            >
                <div class="checks-group">
                    <div class="checks-heading">${this._interpolateLabel(this.labelFailingChecks, { count: failingChecks.length })}</div>
                    ${failingChecks.map(check => this._renderCheck(check))}
                </div>

                <details class="checks-group">
                    <summary class="checks-heading">${this._interpolateLabel(this.labelPassingChecks, { count: passingChecks.length })}</summary>
                    ${passingChecks.map(check => this._renderCheck(check))}
                </details>
            </div>
        `;
    }

    /**
     * @param {Object} check
     * @returns {import('lit').TemplateResult}
     */
    _renderCheck(check) {
        const emoji = check.passing ? '✅' : '❌';
        return html`
            <details class="check">
                <summary>
                    <span style="flex: 1">${emoji} ${check.description}</span>
                    <span class="check-points">${this._interpolateLabel(this.labelPoints, { score: check.score })}</span>
                    <span class="check-chevron" aria-hidden="true">${OlScorecard._chevronIcon}</span>
                </summary>
                <div class="check-details">${check.details}</div>
            </details>
        `;
    }
}

customElements.define('ol-scorecard', OlScorecard);
