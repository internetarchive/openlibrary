import { addModeInputsToForm, mode as searchMode, normalizeMode } from './SearchUtils';
import $ from 'jquery';

/** @typedef {import('./SearchUtils').SearchModeSelector} SearchModeSelector */

/** Manages some (PROBABLY VERY FEW) of the interactions on the search page */
export class SearchPage {
    /**
     * @param {HTMLFormElement|JQuery} form the .olform search form
     * @param {SearchModeSelector} searchModeSelector
     * @param {Object} [urlParams] parsed URL parameters
     */
    constructor(form, searchModeSelector, urlParams={}) {
        this.$form = $(form);
        this._urlMode = normalizeMode(urlParams.mode);
        // Don't init from localStorage — use URL mode; clear after user radio interaction
        searchMode.sync(() => {
            this._urlMode = null;           // user clicked radio → stop overriding with URL mode
            this.updateModeInputs();
        }, false);
        this.updateModeInputs();            // initial render using URL mode
        this.$form.on('submit', this.updateModeInputs.bind(this));
        searchModeSelector.change(() => this.$form.trigger('submit'));
    }

    /** Convenience wrapper of {@link addModeInputsToForm} */
    updateModeInputs() {
        addModeInputsToForm(this.$form, this._urlMode || searchMode.read());
    }
}
