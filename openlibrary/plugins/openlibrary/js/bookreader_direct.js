// Make Borrow links act as if POSTing to Borrow page

jQuery(function() {
    // TODO: After update jQuery, will need to get rid of deprecated .live()
    $('.borrow-link').live('click', function(event) {
        event.preventDefault();
        var $this = $(this);
        var borrowUrl = $this.attr('href').replace(/'/g, '%27');
        var borrowFormString = "<form action='" + borrowUrl + "' method='POST'>\n" +
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
});
