"""Generic date utilities.
"""
import datetime

def parse_date(datestr):
    """Parses date string.
    
        >>> parse_date("2010")
        datetime.date(2010, 01, 01)
        >>> parse_date("2010-02")
        datetime.date(2010, 02, 01)
        >>> parse_date("2010-02-04")
        datetime.date(2010, 02, 04)
    """
    tokens = datestr.split("-")
    _resize_list(tokens, 3)
    
    yyyy, mm, dd = tokens[:3]
    return datetime.date(int(yyyy), mm and int(mm) or 1, dd and int(dd) or 1)
    
def parse_daterange(datestr):
    """Parses date range.
        
        >>> parse_daterange("2010-02")
        (datetime.date(2010, 02, 01), datetime.date(2010, 03, 01))
    """
    date = parse_date(datestr)
    tokens = datestr.split("-")
    
    if len(tokens) == 1: # only year specified
        return date, nextyear(date)
    elif len(tokens) == 2: # year and month specified
        return date, nextmonth(date)
    else:
        return date, nextday(date)
    
def nextday(date):
    return date + datetime.timedelta(1)

def nextmonth(date):
    """Returns a new date object with first day of the next month."""
    year, month = date.year, date.month
    month = month + 1
    
    if month > 12:
        month = 1
        year += 1
         
    return datetime.date(year, month, 1)

def nextyear(date):
    """Returns a new date object with first day of the next year."""
    return datetime.date(date.year+1, 1, 1)

def _resize_list(x, size):
    """Increase the size of the list x to the specified size it is smaller.
    """
    if len(x) < size:
        x += [None] * (size - len(x))
