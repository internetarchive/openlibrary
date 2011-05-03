import datetime

def test_create_case(couchdb, sequence):
    "Tries to create a case"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    
    s = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    assert s.caseid == "case-0"
    assert s.creator_name == "Noufal Ibrahim"
    assert s.creator_email == "noufal@archive.org"
    assert s.creator_useragent == "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)"
    assert s.subject == "Testing"
    assert s.description == "This is a test request"
    assert s.assignee == "anand@archive.org"
    created_date = s.created
    current_date = datetime.datetime.utcnow()
    assert created_date.day == current_date.day
    assert created_date.month == current_date.month
    assert created_date.year == current_date.year




    
