from .. import dateutil
import datetime

def test_parse_date():
    assert dateutil.parse_date("2010") == datetime.date(2010, 1, 1)
    assert dateutil.parse_date("2010-02") == datetime.date(2010, 2, 1)
    assert dateutil.parse_date("2010-02-03") == datetime.date(2010, 2, 3)
    
def test_nextday():
    assert dateutil.nextday(datetime.date(2008, 1, 1)) == datetime.date(2008, 1, 2)
    assert dateutil.nextday(datetime.date(2008, 1, 31)) == datetime.date(2008, 2, 1)
    
    assert dateutil.nextday(datetime.date(2008, 2, 28)) == datetime.date(2008, 2, 29)
    assert dateutil.nextday(datetime.date(2008, 2, 29)) == datetime.date(2008, 3, 1)
    
    assert dateutil.nextday(datetime.date(2008, 12, 31)) == datetime.date(2009, 1, 1)
    
def test_nextmonth():
    assert dateutil.nextmonth(datetime.date(2008, 1, 1)) == datetime.date(2008, 2, 1)
    assert dateutil.nextmonth(datetime.date(2008, 1, 12)) == datetime.date(2008, 2, 1)
    
    assert dateutil.nextmonth(datetime.date(2008, 12, 12)) == datetime.date(2009, 1, 1)

def test_nextyear():
    assert dateutil.nextyear(datetime.date(2008, 1, 1)) == datetime.date(2009, 1, 1)
    assert dateutil.nextyear(datetime.date(2008, 2, 12)) == datetime.date(2009, 1, 1)

def test_parse_daterange():
    assert dateutil.parse_daterange("2010") == (datetime.date(2010, 1, 1), datetime.date(2011, 1, 1))
    assert dateutil.parse_daterange("2010-02") == (datetime.date(2010, 2, 1), datetime.date(2010, 3, 1))
    assert dateutil.parse_daterange("2010-02-03") == (datetime.date(2010, 2, 3), datetime.date(2010, 2, 4)) 