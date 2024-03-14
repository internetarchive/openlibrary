import { addModeInputsToForm, mode as searchMode } from './SearchUtils';
import $ from 'jquery';

/** @typedef {import('./SearchUtils').SearchModeSelector} SearchModeSelector */

/** Manages some (PROBABLY VERY FEW) of the interactions on the search page */
export class SearchPage {
    /**
     * @param {HTMLFormElement|JQuery} form the .olform search form
     * @param {SearchModeSelector} searchModeSelector
     */
    constructor(form, searchModeSelector) {
        this.$form = $(form);
        searchMode.sync(this.updateModeInputs.bind(this));
        this.$form.on('submit', this.updateModeInputs.bind(this));
        searchModeSelector.change(() => this.$form.trigger('submit'));
    }

    /** Convenience wrapper of {@link addModeInputsToForm} */
    updateModeInputs() {
        addModeInputsToForm(this.$form, searchMode.read());
    }
}
