#!/usr/bin/env python
"""Utility script to list html files which might be missing i18n strings."""
import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import re
import sys
from pathlib import Path
from enum import Enum
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

EXCLUDE_LIST = [
    "openlibrary/macros/AffiliateLinks.html",
    "openlibrary/macros/BookByline.html",
    "openlibrary/macros/BookCount.html",
    "openlibrary/macros/BookPreview.html",
    "openlibrary/macros/BookSearchInside.html",
    "openlibrary/macros/CoverImage.html",
    "openlibrary/macros/CreateListModal.html",
    "openlibrary/macros/DisplayCode.html",
    "openlibrary/macros/DonateModal.html",
    "openlibrary/macros/EditButtons.html",
    "openlibrary/macros/EditionNavBar.html",
    "openlibrary/macros/FlourishButton.html",
    "openlibrary/macros/Follow.html",
    "openlibrary/macros/FormatExpiry.html",
    "openlibrary/macros/FulltextResults.html",
    "openlibrary/macros/FulltextSnippet.html",
    "openlibrary/macros/Hello.html",
    "openlibrary/macros/HelpFormatting.html",
    "openlibrary/macros/HiddenSaveButton.html",
    "openlibrary/macros/IABook.html",
    "openlibrary/macros/ListCarousel.html",
    "openlibrary/macros/LoadingIndicator.html",
    "openlibrary/macros/LoanReadForm.html",
    "openlibrary/macros/LoanStatus.html",
    "openlibrary/macros/ManageLoansButtons.html",
    "openlibrary/macros/ManageWaitlistButton.html",
    "openlibrary/macros/MemberCount.html",
    "openlibrary/macros/Metatags.html",
    "openlibrary/macros/NotInLibrary.html",
    "openlibrary/macros/NotesModal.html",
    "openlibrary/macros/ObservationsModal.html",
    "openlibrary/macros/PageList.html",
    "openlibrary/macros/Pager.html",
    "openlibrary/macros/Pager_loanhistory.html",
    "openlibrary/macros/Paginate.html",
    "openlibrary/macros/Profile.html",
    "openlibrary/macros/QueryCarousel.html",
    "openlibrary/macros/ReadButton.html",
    "openlibrary/macros/ReadMore.html",
    "openlibrary/macros/RecentChanges.html",
    "openlibrary/macros/RecentChangesAdmin.html",
    "openlibrary/macros/RecentChangesUsers.html",
    "openlibrary/macros/ReturnForm.html",
    "openlibrary/macros/SearchNavigation.html",
    "openlibrary/macros/SearchResults.html",
    "openlibrary/macros/SearchResultsWork.html",
    "openlibrary/macros/ShareModal.html",
    "openlibrary/macros/SponsorCarousel.html",
    "openlibrary/macros/StarRatings.html",
    "openlibrary/macros/StarRatingsStats.html",
    "openlibrary/macros/SubjectTags.html",
    "openlibrary/macros/Subnavigation.html",
    "openlibrary/macros/TableOfContents.html",
    "openlibrary/macros/ThingReference.html",
    "openlibrary/macros/TruncateString.html",
    "openlibrary/macros/TypeChanger.html",
    "openlibrary/macros/UserEditRow.html",
    "openlibrary/macros/WorkInfo.html",
    "openlibrary/macros/WorldcatLink.html",
    "openlibrary/macros/WorldcatUrl.html",
    "openlibrary/macros/YouTube.html",
    "openlibrary/macros/databarDiff.html",
    "openlibrary/macros/databarEdit.html",
    "openlibrary/macros/databarHistory.html",
    "openlibrary/macros/databarTemplate.html",
    "openlibrary/macros/databarView.html",
    "openlibrary/macros/databarWork.html",
    "openlibrary/macros/i18n.html",
    "openlibrary/macros/iframe.html",
    "openlibrary/templates/about/index.html",
    "openlibrary/templates/account.html",
    "openlibrary/templates/account/create.html",
    "openlibrary/templates/account/delete.html",
    "openlibrary/templates/account/email/forgot-ia.html",
    "openlibrary/templates/account/email/forgot.html",
    "openlibrary/templates/account/follows.html",
    "openlibrary/templates/account/ia_thirdparty_logins.html",
    "openlibrary/templates/account/import.html",
    "openlibrary/templates/account/loan_history.html",
    "openlibrary/templates/account/loans.html",
    "openlibrary/templates/account/mybooks.html",
    "openlibrary/templates/account/not_verified.html",
    "openlibrary/templates/account/notes.html",
    "openlibrary/templates/account/notifications.html",
    "openlibrary/templates/account/observations.html",
    "openlibrary/templates/account/password/forgot.html",
    "openlibrary/templates/account/password/reset.html",
    "openlibrary/templates/account/password/reset_success.html",
    "openlibrary/templates/account/password/sent.html",
    "openlibrary/templates/account/privacy.html",
    "openlibrary/templates/account/reading_log.html",
    "openlibrary/templates/account/readinglog_shelf_name.html",
    "openlibrary/templates/account/readinglog_stats.html",
    "openlibrary/templates/account/sidebar.html",
    "openlibrary/templates/account/topmenu.html",
    "openlibrary/templates/account/verify.html",
    "openlibrary/templates/account/verify/activated.html",
    "openlibrary/templates/account/verify/failed.html",
    "openlibrary/templates/account/verify/success.html",
    "openlibrary/templates/account/view.html",
    "openlibrary/templates/account/yrg_banner.html",
    "openlibrary/templates/admin/attach_debugger.html",
    "openlibrary/templates/admin/block.html",
    "openlibrary/templates/admin/graphs.html",
    "openlibrary/templates/admin/history.html",
    "openlibrary/templates/admin/imports-add.html",
    "openlibrary/templates/admin/imports.html",
    "openlibrary/templates/admin/imports_by_date.html",
    "openlibrary/templates/admin/index.html",
    "openlibrary/templates/admin/inspect/memcache.html",
    "openlibrary/templates/admin/inspect/store.html",
    "openlibrary/templates/admin/ip/index.html",
    "openlibrary/templates/admin/ip/view.html",
    "openlibrary/templates/admin/loans.html",
    "openlibrary/templates/admin/loans_table.html",
    "openlibrary/templates/admin/memory/index.html",
    "openlibrary/templates/admin/memory/object.html",
    "openlibrary/templates/admin/memory/type.html",
    "openlibrary/templates/admin/menu.html",
    "openlibrary/templates/admin/people/edits.html",
    "openlibrary/templates/admin/people/index.html",
    "openlibrary/templates/admin/people/view.html",
    "openlibrary/templates/admin/permissions.html",
    "openlibrary/templates/admin/solr.html",
    "openlibrary/templates/admin/spamwords.html",
    "openlibrary/templates/admin/sponsorship.html",
    "openlibrary/templates/admin/sync.html",
    "openlibrary/templates/authors/index.html",
    "openlibrary/templates/authors/infobox.html",
    "openlibrary/templates/barcodescanner.html",
    "openlibrary/templates/book_providers/cita_press_download_options.html",
    "openlibrary/templates/book_providers/cita_press_read_button.html",
    "openlibrary/templates/book_providers/gutenberg_download_options.html",
    "openlibrary/templates/book_providers/gutenberg_read_button.html",
    "openlibrary/templates/book_providers/ia_download_options.html",
    "openlibrary/templates/book_providers/librivox_download_options.html",
    "openlibrary/templates/book_providers/librivox_read_button.html",
    "openlibrary/templates/book_providers/openstax_download_options.html",
    "openlibrary/templates/book_providers/openstax_read_button.html",
    "openlibrary/templates/book_providers/standard_ebooks_download_options.html",
    "openlibrary/templates/book_providers/standard_ebooks_read_button.html",
    "openlibrary/templates/books/RelatedWorksCarousel.html",
    "openlibrary/templates/books/add.html",
    "openlibrary/templates/books/author-autocomplete.html",
    "openlibrary/templates/books/breadcrumb_select.html",
    "openlibrary/templates/books/check.html",
    "openlibrary/templates/books/custom_carousel.html",
    "openlibrary/templates/books/daisy.html",
    "openlibrary/templates/books/edit.html",
    "openlibrary/templates/books/edit/about.html",
    "openlibrary/templates/books/edit/edition.html",
    "openlibrary/templates/books/edit/excerpts.html",
    "openlibrary/templates/books/edit/web.html",
    "openlibrary/templates/books/edition-sort.html",
    "openlibrary/templates/books/mobile_carousel.html",
    "openlibrary/templates/books/mybooks_breadcrumb_select.html",
    "openlibrary/templates/books/show.html",
    "openlibrary/templates/books/works-show.html",
    "openlibrary/templates/books/year_breadcrumb_select.html",
    "openlibrary/templates/check_ins/check_in_form.html",
    "openlibrary/templates/check_ins/check_in_prompt.html",
    "openlibrary/templates/check_ins/reading_goal_form.html",
    "openlibrary/templates/check_ins/reading_goal_progress.html",
    "openlibrary/templates/contact/spam/sent.html",
    "openlibrary/templates/covers/add.html",
    "openlibrary/templates/covers/author_photo.html",
    "openlibrary/templates/covers/book_cover.html",
    "openlibrary/templates/covers/book_cover_single_edition.html",
    "openlibrary/templates/covers/book_cover_small.html",
    "openlibrary/templates/covers/book_cover_work.html",
    "openlibrary/templates/covers/change.html",
    "openlibrary/templates/covers/manage.html",
    "openlibrary/templates/covers/saved.html",
    "openlibrary/templates/design.html",
    "openlibrary/templates/diff.html",
    "openlibrary/templates/edit_yaml.html",
    "openlibrary/templates/editpage.html",
    "openlibrary/templates/email/account/verify.html",
    "openlibrary/templates/email/case_created.html",
    "openlibrary/templates/email/case_notification.html",
    "openlibrary/templates/email/password/reminder.html",
    "openlibrary/templates/email/spam_report.html",
    "openlibrary/templates/email/support_case.html",
    "openlibrary/templates/email/waitinglist_book_available.html",
    "openlibrary/templates/email/waitinglist_people_waiting.html",
    "openlibrary/templates/form.html",
    "openlibrary/templates/history.html",
    "openlibrary/templates/history/comment.html",
    "openlibrary/templates/history/sources.html",
    "openlibrary/templates/home/about.html",
    "openlibrary/templates/home/categories.html",
    "openlibrary/templates/home/custom_ia_carousel.html",
    "openlibrary/templates/home/index.html",
    "openlibrary/templates/home/loans.html",
    "openlibrary/templates/home/onboarding_card.html",
    "openlibrary/templates/home/popular.html",
    "openlibrary/templates/home/returncart.html",
    "openlibrary/templates/home/stats.html",
    "openlibrary/templates/home/welcome.html",
    "openlibrary/templates/internalerror.html",
    "openlibrary/templates/jsdef/LazyAuthorPreview.html",
    "openlibrary/templates/jsdef/LazyWorkPreview.html",
    "openlibrary/templates/languages/index.html",
    "openlibrary/templates/languages/language_list.html",
    "openlibrary/templates/languages/notfound.html",
    "openlibrary/templates/lib/dropper.html",
    "openlibrary/templates/lib/edit_head.html",
    "openlibrary/templates/lib/header_dropdown.html",
    "openlibrary/templates/lib/history.html",
    "openlibrary/templates/lib/message_addbook.html",
    "openlibrary/templates/lib/nav_foot.html",
    "openlibrary/templates/lib/nav_head.html",
    "openlibrary/templates/lib/not_logged.html",
    "openlibrary/templates/lib/pagination.html",
    "openlibrary/templates/lib/subnavigation.html",
    "openlibrary/templates/lib/view_head.html",
    "openlibrary/templates/library_explorer.html",
    "openlibrary/templates/lists/activity.html",
    "openlibrary/templates/lists/dropper_lists.html",
    "openlibrary/templates/lists/export_as_bibtex.html",
    "openlibrary/templates/lists/export_as_html.html",
    "openlibrary/templates/lists/feed_updates.html",
    "openlibrary/templates/lists/header.html",
    "openlibrary/templates/lists/home.html",
    "openlibrary/templates/lists/list_overview.html",
    "openlibrary/templates/lists/lists.html",
    "openlibrary/templates/lists/preview.html",
    "openlibrary/templates/lists/showcase.html",
    "openlibrary/templates/lists/snippet.html",
    "openlibrary/templates/lists/widget.html",
    "openlibrary/templates/login.html",
    "openlibrary/templates/merge/authors.html",
    "openlibrary/templates/merge/works.html",
    "openlibrary/templates/merge_request_table/merge_request_table.html",
    "openlibrary/templates/merge_request_table/table_header.html",
    "openlibrary/templates/merge_request_table/table_row.html",
    "openlibrary/templates/message.html",
    "openlibrary/templates/messages.html",
    "openlibrary/templates/my_books/dropdown_content.html",
    "openlibrary/templates/my_books/dropper.html",
    "openlibrary/templates/my_books/primary_action.html",
    "openlibrary/templates/native_dialog.html",
    "openlibrary/templates/notfound.html",
    "openlibrary/templates/observations/review_component.html",
    "openlibrary/templates/permission.html",
    "openlibrary/templates/permission_denied.html",
    "openlibrary/templates/publishers/index.html",
    "openlibrary/templates/publishers/notfound.html",
    "openlibrary/templates/publishers/view.html",
    "openlibrary/templates/recaptcha.html",
    "openlibrary/templates/recentchanges/add-book/comment.html",
    "openlibrary/templates/recentchanges/add-book/path.html",
    "openlibrary/templates/recentchanges/default/comment.html",
    "openlibrary/templates/recentchanges/default/message.html",
    "openlibrary/templates/recentchanges/default/path.html",
    "openlibrary/templates/recentchanges/default/view.html",
    "openlibrary/templates/recentchanges/edit-book/comment.html",
    "openlibrary/templates/recentchanges/edit-book/message.html",
    "openlibrary/templates/recentchanges/edit-book/path.html",
    "openlibrary/templates/recentchanges/header.html",
    "openlibrary/templates/recentchanges/index.html",
    "openlibrary/templates/recentchanges/lists/comment.html",
    "openlibrary/templates/recentchanges/lists/message.html",
    "openlibrary/templates/recentchanges/merge/comment.html",
    "openlibrary/templates/recentchanges/merge/message.html",
    "openlibrary/templates/recentchanges/merge/path.html",
    "openlibrary/templates/recentchanges/merge/view.html",
    "openlibrary/templates/recentchanges/new-account/path.html",
    "openlibrary/templates/recentchanges/render.html",
    "openlibrary/templates/recentchanges/undo/view.html",
    "openlibrary/templates/recentchanges/updated_records.html",
    "openlibrary/templates/search/advancedsearch.html",
    "openlibrary/templates/search/authors.html",
    "openlibrary/templates/search/inside.html",
    "openlibrary/templates/search/lists.html",
    "openlibrary/templates/search/publishers.html",
    "openlibrary/templates/search/snippets.html",
    "openlibrary/templates/search/sort_options.html",
    "openlibrary/templates/search/subjects.html",
    "openlibrary/templates/search/work_search_facets.html",
    "openlibrary/templates/showamazon.html",
    "openlibrary/templates/showbwb.html",
    "openlibrary/templates/showia.html",
    "openlibrary/templates/showmarc.html",
    "openlibrary/templates/site.html",
    "openlibrary/templates/site/alert.html",
    "openlibrary/templates/site/around_the_library.html",
    "openlibrary/templates/site/banner.html",
    "openlibrary/templates/site/body.html",
    "openlibrary/templates/site/donate.html",
    "openlibrary/templates/site/footer.html",
    "openlibrary/templates/site/head.html",
    "openlibrary/templates/site/neck.html",
    "openlibrary/templates/site/stats.html",
    "openlibrary/templates/stats/readinglog.html",
    "openlibrary/templates/status.html",
    "openlibrary/templates/subjects.html",
    "openlibrary/templates/subjects/notfound.html",
    "openlibrary/templates/support.html",
    "openlibrary/templates/swagger/swaggerui.html",
    "openlibrary/templates/tag/add.html",
    "openlibrary/templates/trending.html",
    "openlibrary/templates/type/about/edit.html",
    "openlibrary/templates/type/about/view.html",
    "openlibrary/templates/type/author/edit.html",
    "openlibrary/templates/type/author/input.html",
    "openlibrary/templates/type/author/rdf.html",
    "openlibrary/templates/type/author/repr.html",
    "openlibrary/templates/type/author/view.html",
    "openlibrary/templates/type/content/edit.html",
    "openlibrary/templates/type/content/view.html",
    "openlibrary/templates/type/delete/view.html",
    "openlibrary/templates/type/edition/admin_bar.html",
    "openlibrary/templates/type/edition/compact_title.html",
    "openlibrary/templates/type/edition/modal_links.html",
    "openlibrary/templates/type/edition/rdf.html",
    "openlibrary/templates/type/edition/title_and_author.html",
    "openlibrary/templates/type/edition/view.html",
    "openlibrary/templates/type/home/edit.html",
    "openlibrary/templates/type/homepage/view.html",
    "openlibrary/templates/type/i18n_page/edit.html",
    "openlibrary/templates/type/i18n_page/view.html",
    "openlibrary/templates/type/language/input.html",
    "openlibrary/templates/type/language/repr.html",
    "openlibrary/templates/type/language/view.html",
    "openlibrary/templates/type/list/edit.html",
    "openlibrary/templates/type/list/embed.html",
    "openlibrary/templates/type/list/exports.html",
    "openlibrary/templates/type/list/view.html",
    "openlibrary/templates/type/list/view_body.html",
    "openlibrary/templates/type/local_id/view.html",
    "openlibrary/templates/type/object/view.html",
    "openlibrary/templates/type/page/edit.html",
    "openlibrary/templates/type/page/view.html",
    "openlibrary/templates/type/permission/edit.html",
    "openlibrary/templates/type/permission/view.html",
    "openlibrary/templates/type/tag/edit.html",
    "openlibrary/templates/type/tag/view.html",
    "openlibrary/templates/type/template/edit.html",
    "openlibrary/templates/type/template/view.html",
    "openlibrary/templates/type/type/view.html",
    "openlibrary/templates/type/user/edit.html",
    "openlibrary/templates/type/user/view.html",
    "openlibrary/templates/type/usergroup/edit.html",
    "openlibrary/templates/type/work/editions.html",
    "openlibrary/templates/type/work/editions_datatable.html",
    "openlibrary/templates/type/work/rdf.html",
    "openlibrary/templates/type/work/repr.html",
    "openlibrary/templates/viewpage.html",
    "openlibrary/templates/widget.html",
    "openlibrary/templates/work_search.html",
]

valid_directories = ['openlibrary/templates/', 'openlibrary/macros/']


class Errtype(str, Enum):
    WARN = "\033[93mWARN\033[0m"
    ERR = "\033[91mERRO\033[0m"
    SKIP = "\033[94mSKIP\033[0m"


skip_directive = r"# detect-missing-i18n-skip-line"
regex_skip_inline = r"\$" + skip_directive
regex_skip_previous_line = r"^\s*\$?" + skip_directive

# Assumptions:
# - Not concerned about HTML elements whose untranslated contents follow a newline, i.e. <p>\nsome untranslated text\n<p>.
# - Don't want to flag false positives where > characters are not part of tags, so this regex looks for a complete opening tag.
# TODO: replace the huge punctuation array with \p{L} - only supported in pip regex and not re
punctuation = r"[\(\)\{\}\[\]\/\\:;\-_\s+=*^%#\.•·\?♥|≡0-9,!xX✓×@\"'†★]"
htmlents = r"&[a-z0-9]+;"
variables = r"\$:?[^\s]+|\$[^\s\(]+[\(][^\)]+[\)]|\$[^\s\[]+[\[][^\]]+[\]]|\$[\{][^\}]+[\}]|%\(?[a-z_]+\)?|\{\{[^\}]+\}\}"
urls_domains = r"https?:\/\/[^\s]+|[a-z\-]+\.[A-Za-z]{2}[a-z]?"

opening_tag_open = r"<(?!code|link|!--)[a-z][^>]*?"
opening_tag_end = r"[^\/\-\s]>"
opening_tag_syntax = opening_tag_open + opening_tag_end
ignore_after_opening_tag = (
    r"(?![<\r\n]|$|\\\$\$|\$:?_?\(|\$:?ungettext\(|(?:"
    + punctuation
    + r"|"
    + htmlents
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")+(?:[\r\n<]|$))"
)

i18n_element_missing_regex = opening_tag_syntax + ignore_after_opening_tag
i18n_element_warn_regex = opening_tag_syntax + r"\$\((?!_\()"

attr_syntax = r"(title|placeholder|alt)="
ignore_double_quote = (
    r"\"(?!\$:?_?\(|\$:?ungettext\(|\\\$\$|(?:"
    + punctuation
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")*\")"
)
ignore_single_quote = (
    r"\'(?!\$:?_?\(|\$:?ungettext\(|\\\$\$|(?:"
    + punctuation
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")*\')"
)

i18n_attr_missing_regex = (
    opening_tag_open
    + attr_syntax
    + r"(?:"
    + ignore_double_quote
    + r"|"
    + ignore_single_quote
    + r")[^>]*?>"
)
i18n_attr_warn_regex = opening_tag_open + attr_syntax + r"['\"]\$\((?!_\()"


def terminal_underline(text: str) -> str:
    return f"\033[4m{text}\033[0m"


def print_analysis(
    errtype: str,
    filename: str,
    details: str,
    spacing_base: int,
    line_number: int = 0,
    line_position: int = 0,
):
    linestr = (
        f":{line_number}:{line_position}"
        if line_number > 0 and line_position > 0
        else ""
    )
    filestring = f'{filename}{linestr}'
    print(
        '\t'.join(
            [errtype, terminal_underline(filestring).ljust(spacing_base + 12), details]
        )
    )


def main(files: list[Path], skip_excluded: bool = True):
    """
    :param files: The html files to check for missing i18n
    :param skip_excluded: If --no-skip-excluded is supplied as an arg, files in the EXCLUDE_LIST slice will be processed
    """

    # Don't validate i18n unless the file is in one of the valid_directories.
    valid_files = [
        file
        for file in files
        if len([valid for valid in valid_directories if str(file).startswith(valid)])
        > 0
    ]
    if len(valid_files) == 0:
        sys.exit(0)

    # Figure out how much padding to put between the filename and the error output
    longest_filename_length = max(len(str(f)) for f in valid_files)
    spacing_base = longest_filename_length + len(':XXX:XXX')

    errcount: int = 0
    warnings: int = 0

    for file in valid_files:

        contents = file.read_text()
        lines = contents.splitlines()

        if str(file) in EXCLUDE_LIST and skip_excluded:
            print_analysis(Errtype.SKIP, str(file), "", spacing_base)
            continue

        for line_number, line in enumerate(lines, start=1):

            includes_error_element = re.search(i18n_element_missing_regex, line)
            includes_warn_element = re.search(i18n_element_warn_regex, line)
            includes_error_attribute = re.search(i18n_attr_missing_regex, line)
            includes_warn_attribute = re.search(i18n_attr_warn_regex, line)

            char_index = -1
            # Element with untranslated elements
            if includes_error_element:
                char_index = includes_error_element.start()
                errtype = Errtype.ERR
                errcount += 1
            # Element with bypassed elements
            elif includes_warn_element:
                char_index = includes_warn_element.start()
                errtype = Errtype.WARN
                warnings += 1
            # Element with untranslated attributes
            elif includes_error_attribute:
                char_index = includes_error_attribute.start()
                errtype = Errtype.ERR
                errcount += 1
            # Element with bypassed attributes
            elif includes_warn_attribute:
                char_index = includes_warn_attribute.start()
                errtype = Errtype.WARN
                warnings += 1

            # Don't proceed if the line doesn't match any of the four cases.
            if char_index == -1:
                continue

            preceding_text = line[:char_index]
            regex_match = line[char_index:]

            # Don't proceed if the line is likely commented out or part of a $: function.
            if "<!--" in preceding_text or "$:" in preceding_text:
                continue

            # Don't proceed if skip directive is included inline.
            if re.search(regex_skip_inline, regex_match):
                continue

            # Don't proceed if the previous line is a skip directive.
            if re.match(regex_skip_previous_line, lines[line_number - 2]):
                continue

            print_position = char_index + 1
            print_analysis(
                errtype,
                str(file),
                regex_match,
                spacing_base,
                line_number,
                print_position,
            )

    print(
        f"{len(valid_files)} file{'s' if len(valid_files) != 1 else ''} scanned. {errcount} error{'s' if errcount != 1 else ''} found."
    )
    if errcount > 0 or warnings > 0:
        print(
            "Learn how to fix these errors by reading our i18n documentation: https://github.com/internetarchive/openlibrary/wiki/Internationalization#internationalization-i18n-developers-guide"
        )

    if errcount > 0:
        sys.exit(1)


if __name__ == "__main__":
    FnToCLI(main).run()
