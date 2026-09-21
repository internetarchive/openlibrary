"""What `macros/LoanActions.html` offers for each kind of loan (#13687).

The interesting case is the one that is *not* an Internet Archive loan. Before
this macro existed the dispatch lived inline in
`templates/account/loans.html`, where the only way to reach it was to render
the whole loans page -- a mock site, covers, a waiting list -- so nothing
reached it. #13690 is what that costs: an unhandled acquisition fell off the
end of the if/elif chain in `book_providers/read_button.html` and rendered the
empty string, with the provider correctly registered and the patron shown
nothing.
"""

import pytest
import web

IA_LOAN = {
    "book": "/books/OL1M",
    "ocaid": "someocaid",
    "expiry": "2026-10-01T00:00:00",
    "resource_type": "bookreader",
    "loaned_at": 1.0,
}

PROVIDER_LOAN = {
    "book": "/books/OL37044497M",
    "loaned_at": 0.0,
    "expiry": "2026-10-01T00:00:00",
    "userid": "ol:patron",
    "provider": "lenny",
    "resource_type": "provider",
    "read_url": "https://lennyforlibraries.org/v1/api/items/37044497/read",
}
"""Note `expiry` is naive, and that is load-bearing rather than incidental.

The node sends an offset; `lenny._expiry` strips it precisely because this
template's parser cannot read one. An earlier version of this fixture was
naive because that is the value that happens to parse, so the fixture agreed
with the code instead of testing it -- which is why
`TestTheExpiryTheNodeActuallySends` below feeds the raw node shape through
`loan_from_node` rather than hand-writing the normalised result.
"""


@pytest.fixture
def render_actions(render_template, request_context_fixture):
    from infogami.utils import macro

    # `macros/` is not on the disk source the render_template fixture builds;
    # only `templates/` is. The Internet Archive branch calls two macros, so
    # without this the IA cases below would fail for a reason that has nothing
    # to do with what they assert.
    macro.diskmacros.load_templates("openlibrary/macros")

    request_context_fixture(lang="en")
    web.ctx.path = "/account/loans"
    web.ctx.fullpath = "/account/loans"
    web.template.Template.globals["request"] = web.storage(fullpath="/account/loans")

    def render(loan):
        return render_template("account/loan_actions", loan)

    return render


class TestAProviderLoanIsNotAnInternetArchiveLoan:
    def test_it_offers_the_node_reader(self, render_actions):
        out = render_actions(PROVIDER_LOAN)
        assert "https://lennyforlibraries.org/v1/api/items/37044497/read" in out
        assert "Read" in out

    def test_it_does_not_reach_the_adobe_branch(self, render_actions):
        """The `else` arm of the resource_type chain reads `loan['loan_link']`,
        which a provider loan does not have -- a KeyError on the patron's own
        loans page -- and tells them to return the book through Adobe Digital
        Editions, which is wrong even where it does not raise."""
        out = render_actions(PROVIDER_LOAN)
        assert "Adobe Digital Editions" not in out
        assert "Download Now" not in out

    def test_it_does_not_render_an_internet_archive_return_form(self, render_actions):
        """`/borrow/ia/<ocaid>` would be aimed at a loan the Internet Archive
        has never heard of."""
        out = render_actions(PROVIDER_LOAN)
        assert "/borrow/ia/" not in out

    def test_it_names_the_library_the_book_came_from(self, render_actions):
        assert "lenny" in render_actions(PROVIDER_LOAN)

    def test_it_renders_something(self, render_actions):
        """#13690's actual failure was not an exception: the chain simply ran
        out of branches and returned whitespace."""
        assert render_actions(PROVIDER_LOAN).strip() != ""

    def test_a_provider_loan_with_no_due_date_still_renders(self, render_actions):
        """`due_at` is documented nullable."""
        out = render_actions({**PROVIDER_LOAN, "expiry": None})
        assert "/v1/api/items/37044497/read" in out


class TestTheExpiryTheNodeActuallySends:
    """The raw node payload through both halves, which is the gap the unit
    tests left.

    `test_lenny.py` proved `loan_from_node` normalises the offset, and the
    tests above proved the template renders a loan whose expiry is already
    normalised. Neither noticed that nothing connected them, because both
    sides were handed the value that happens to parse. Rendering what
    `loan_from_node` actually returns from what the node actually sends is the
    only arrangement in which the defect is visible.
    """

    @staticmethod
    def _from_node(due_at):
        from openlibrary.plugins.upstream import lenny

        loan = lenny.loan_from_node("lenny", "https://lennyforlibraries.org", "patron", {"edition_id": 37044497, "due_at": due_at})
        assert loan is not None
        return loan

    @pytest.mark.parametrize(
        "due_at",
        [
            "2026-10-01T00:00:00+00:00",
            "2026-10-01T00:00:00Z",
            "2026-09-30T17:00:00-07:00",
            "2026-10-01T00:00:00+05:30",
            None,
        ],
    )
    def test_the_page_renders_for_every_offset_a_node_can_send(self, render_actions, due_at):
        out = render_actions(self._from_node(due_at))
        assert "/v1/api/items/37044497/read" in out

    def test_an_unparsable_due_at_drops_the_expiry_rather_than_the_page(self, render_actions):
        out = render_actions(self._from_node("whenever"))
        assert "/v1/api/items/37044497/read" in out


class TestTheInternetArchiveBranchIsUnchanged:
    def test_a_bookreader_loan_still_gets_its_forms(self, render_actions):
        out = render_actions(IA_LOAN)
        assert "/borrow/ia/someocaid" in out
        assert "Return book" in out

    def test_a_bookreader_loan_is_not_treated_as_a_provider_loan(self, render_actions):
        assert "Borrowed from" not in render_actions(IA_LOAN)

    def test_an_undownloaded_acs_loan_still_offers_its_link(self, render_actions):
        acs = {"resource_type": "pdf", "expiry": None, "loan_link": "https://acs.example.org/fulfil"}
        out = render_actions(acs)
        assert "https://acs.example.org/fulfil" in out
        assert "Adobe Digital Editions" in out
