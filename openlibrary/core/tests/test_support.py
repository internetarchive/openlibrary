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

def test_sequence_numbers(couchdb, sequence):
    "Creates a bunch of cases and checks their case numbers"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    for i in range(0,10):
        c = s.create_case(creator_name      = "Noufal Ibrahim",
                          creator_email     = "noufal@archive.org",
                          creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                          subject           = "Testing",
                          description       = "This is a test request",
                          assignee          = "anand@archive.org")
        assert c.caseid == "case-%d"%i

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


def test_readback(couchdb, sequence):
    "Test all ways of reading the case back"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    
    c0 = s.get_case("case-0") #Full string id
    c1 = s.get_case(0)        #Numeric id
    c2 = s.get_case("0")      #Partial string id
    assert c0 == c1 == c2
    assert c0.caseid == "case-0"
    

def test_change_status(couchdb, sequence):
    "Check the API to change case statuses"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    assert c.caseid == "case-0"
    assert c.status == "new"
    c.change_status("assigned", "mary@archive.org")
    c = s.get_case("case-0")
    assert c.status == "assigned"
    entry = c.history[-1]
    assert entry.by == "mary@archive.org"
    assert entry.text == "Case status changed to 'assigned'"
        

def test_reassign(couchdb, sequence):
    "Checks if the case can be reassigned"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    assert c.caseid == "case-0"
    assert c.assignee == "anand@archive.org"
    c.reassign("george@archive.org", "mary@archive.org")
    c = s.get_case("case-0")
    assert c.assignee == "george@archive.org"
    entry = c.history[-1]
    assert entry.by == "mary@archive.org"
    assert entry.text == "Case reassigned to 'george@archive.org'"

def test_add_worklog_entry(couchdb, sequence):
    "Checks if we can add worklog entries"
    from openlibrary.core import support
    s = support.Support(db = couchdb)
    c = s.create_case(creator_name      = "Noufal Ibrahim",
                      creator_email     = "noufal@archive.org",
                      creator_useragent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.18) Gecko/20110323 Iceweasel/3.5.18 (like Firefox/3.5.18)",
                      subject           = "Testing",
                      description       = "This is a test request",
                      assignee          = "anand@archive.org")
    assert c.caseid == "case-0"
    assert len(c.history) == 1
    c.add_worklog_entry("george@archive.org", "Test entry")
    c = s.get_case(0)
    assert len(c.history) == 2
    entry = c.history[-1]
    assert entry.by == "george@archive.org"
    assert entry.text == "Test entry"

    
