import { LitElement, html, css } from 'lit';

/**
 * ol-smoke-status - A web component for displaying smoke test results
 *
 * Fetches data from /smoke.json endpoint and displays:
 * - Number of tests passed/total
 * - Average response time
 * - Time since last test run
 * - Color-coded status (green for all pass, red for any fail)
 * - Clickable link to full results
 *
 * @example
 * <ol-smoke-status></ol-smoke-status>
 */
export class SmokeTestStatus extends LitElement {
    static properties = {
        _data: { type: Object, state: true },
        _loading: { type: Boolean, state: true },
        _error: { type: String, state: true },
        _timeAgo: { type: String, state: true },
        _smokeTestUrl: { type: String, state: true },
    };

    static styles = css`
    :host {
      display: inline-block;
      font-family:
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
      font-size: 14px;
      min-width: 280px;
      min-height: 44px;
      box-sizing: border-box;
    }

    .status {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 12px 16px;
      background: #f5f5f5;
      border-radius: 8px;
      border: 1px solid #e0e0e0;
      min-width: 280px;
    }

    .status:hover {
      background: #ebebeb;
    }

    .indicator {
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }

    .indicator.passed {
      background: #22c55e;
    }

    .indicator.failed {
      background: #dc3545;
    }

    .indicator.loading {
      background: #6c757d;
      animation: pulse 1.5s ease-in-out infinite;
    }

    @keyframes pulse {
      0%,
      100% {
        opacity: 1;
      }
      50% {
        opacity: 0.5;
      }
    }

    .info {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .summary {
      font-weight: 500;
      color: #333;
    }

    .meta {
      font-size: 12px;
      color: #666;
    }

    .link {
      text-decoration: none;
    }
  `;

    constructor() {
        super();
        this._data = null;
        this._loading = true;
        this._error = null;
        this._timeAgo = '';
        this._intervalId = null;
        this._smokeTestUrl = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this._fetchData();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._intervalId) {
            clearInterval(this._intervalId);
        }
    }

    _getSmokeTestUrl() {
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return 'http://localhost:18080/smoke.json';
        } else if (hostname === 'testing.openlibrary.org') {
            return 'https://testing.openlibrary.org/_fast/smoke.json';
        }
        return '/_fast/smoke.json';
    }

    async _fetchData() {
        try {
            this._smokeTestUrl = this._getSmokeTestUrl();
            const response = await fetch(this._smokeTestUrl);
            this._data = await response.json();
            this._error = null;
            this._startTimer();
        } catch (e) {
            this._error = 'Failed to load smoke tests';
        } finally {
            this._loading = false;
        }
    }

    _startTimer() {
        this._updateTimeAgo();
        this._intervalId = setInterval(() => this._updateTimeAgo(), 1000);
    }

    _updateTimeAgo() {
        if (!this._data?.timestamp) return;

        const timestamp = new Date(this._data.timestamp).getTime();
        const now = Date.now();
        const diff = Math.floor((now - timestamp) / 1000);

        if (diff < 60) {
            this._timeAgo = `${diff}s ago`;
        } else if (diff < 3600) {
            this._timeAgo = `${Math.floor(diff / 60)}m ago`;
        } else if (diff < 86400) {
            this._timeAgo = `${Math.floor(diff / 3600)}h ago`;
        } else {
            this._timeAgo = `${Math.floor(diff / 86400)}d ago`;
        }
    }

    _getIndicatorClass() {
        if (this._loading) return 'loading';
        if (this._error) return 'failed';
        if (this._data && this._data.passed === this._data.total) return 'passed';
        return 'failed';
    }

    _getSummaryText() {
        if (this._loading) return 'Loading...';
        if (this._error) return this._error;
        if (!this._data) return '';
        return `${this._data.passed}/${this._data.total} tests passed`;
    }

    _getMetaText() {
        if (this._error || !this._data) return '';
        if (this._loading) return '&nbsp;';
        return `${Math.round(this._data.average_duration_ms)}ms avg · ${this._timeAgo}`;
    }

    render() {
        if (this._loading) {
            return html`
        <div class="status">
          <div class="indicator loading"></div>
          <div class="info">
            <span class="summary">${this._getSummaryText()}</span>
            <span class="meta">${this._getMetaText()}</span>
          </div>
        </div>
      `;
        }

        if (this._error) {
            return html`
        <div class="status">
          <div class="indicator failed"></div>
          <div class="info">
            <span class="summary">${this._error}</span>
          </div>
        </div>
      `;
        }

        if (!this._data) {
            return html``;
        }

        const indicatorClass = this._getIndicatorClass();
        const summaryText = this._getSummaryText();
        const metaText = this._getMetaText();

        return html`
      <a href="${this._smokeTestUrl}" class="link">
        <div class="status">
          <div class="indicator ${indicatorClass}"></div>
          <div class="info">
            <span class="summary">${summaryText}</span>
            ${metaText ? html`<span class="meta">${metaText}</span>` : ''}
          </div>
        </div>
      </a>
    `;
    }
}

customElements.define('ol-smoke-status', SmokeTestStatus);
