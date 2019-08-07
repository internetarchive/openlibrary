import * as SearchUtils from './SearchUtils';

export class SearchPage {
    /**
     * @param {SearchState} searchState
     */
    constructor(searchState) {
        this.searchState = searchState;
        this.searchState.sync('searchMode', () => SearchUtils.updateSearchMode('.olform', this.searchState.searchMode));

        // updateWorkAvailability is defined in openlibrary\openlibrary\plugins\openlibrary\js\availability.js
        // eslint-disable-next-line no-undef
        updateWorkAvailability();

        $('.search-mode').change(event => {
            $('html,body').css('cursor', 'wait');
            this.searchState.searchMode = $(event.target).val();
            if ($('.olform').length) {
                $('.olform').submit();
            } else {
                location.reload();
            }
        });

        $('.olform').submit(() => {
            if (this.searchState.searchMode !== 'everything') {
                $('.olform').append('<input type="hidden" name="has_fulltext" value="true"/>');
            }
            if (this.searchState.searchMode === 'printdisabled') {
                $('.olform').append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
            }
        });
    }
}
