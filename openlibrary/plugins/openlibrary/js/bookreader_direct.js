// Make Borrow links act as if POSTing to Borrow page
export default function() {
    $('.borrow-link').on('click', function(event) {
        var $this, borrowUrl, borrowFormString;
        event.preventDefault();
        $this = $(this);
        borrowUrl = $this.attr('href').replace(/'/g, '%27');
        borrowFormString = "<form action='" + borrowUrl + "' method='POST'>\n" +
      "<input type='hidden' name='action' value='borrow' />\n" +
      "<input type='hidden' name='format' value='bookreader' />\n" +
      "<input type='hidden' name='ol_host' value='" + location.host + "' />\n" +
      "</form>";
        $this.after($(borrowFormString));
        $this.next().submit();
        if (window.archive_analytics) {
            window.archive_analytics.ol_send_event_ping({'category': 'BorrowLink', 'action': 'bookreader'});
        }
    });
}
