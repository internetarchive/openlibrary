import datetime

def test_create_case(couchdb, sequence):
    "Tries to create a case"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    assert c.caseid == "case-0"
    assert c.creator_name == "Noufal Ibrahim"
    assert c.creator_email == "noufal@archive.org"
    assert c.creator_useragent == "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)"
    assert c.subject == "Testing"
    assert c.description == "This is a test request"
    assert c.assignee == "anand@archive.org"
    assert c.status == "new"
    assert c.type == "case"
    created_date = c.created
    current_date = datetime.datetime.utcnow()
    assert created_date.day == current_date.day
    assert created_date.month == current_date.month
    assert created_date.year == current_date.year

def test_history_entry(couchdb, sequence):
    "Test history entries upon creation of a new case"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")    
    entry = c.history[0]
    assert entry.at == c.created
    assert entry.by == "Noufal Ibrahim"
    assert entry.text == "Case created"


    
