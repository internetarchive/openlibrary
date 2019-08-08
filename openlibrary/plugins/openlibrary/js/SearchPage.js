import * as SearchUtils from './SearchUtils';

export class SearchPage {
    constructor() {
        SearchUtils.mode.change(newMode => SearchUtils.updateSearchMode('.olform', newMode));

        // updateWorkAvailability is defined in openlibrary\openlibrary\plugins\openlibrary\js\availability.js
        // eslint-disable-next-line no-undef
        updateWorkAvailability();

        $('.search-mode').change(event => {
            $('html,body').css('cursor', 'wait');
            SearchUtils.mode.write($(event.target).val());
            if ($('.olform').length) {
                $('.olform').submit();
            } else {
                location.reload();
            }
        });

        $('.olform').submit(() => {
            if (SearchUtils.mode.read() !== 'everything') {
                $('.olform').append('<input type="hidden" name="has_fulltext" value="true"/>');
            }
            if (SearchUtils.mode.read() === 'printdisabled') {
                $('.olform').append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
            }
        });
    }
}
