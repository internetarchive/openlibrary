from __future__ import with_statement
import time

OLDEST_PERSON_EVER_IN_CANADA = 117
current_year = int(time.strftime('%Y'))

def mmax(*args):
  """Return maximum of args given, ignoring any None values.  If there are
  no non-None values, return None.
  >>> print mmax()
  None
  >>> print mmax(1)
  1
  >>> print mmax(2,None,4,3)
  4
  >>> print mmax(None,None,None)
  None"""

  a = list(x for x in args if x is not None)
  if len(a) == 0:
    return None
  return max(a)

def copyright_status(edition):
  """Determine copyright status of edition.  Return value is a dictionary containing
  the date at which the edition is conservatively expected to enter the public domain,
  and a list of assumptions made during the calculation."""

  assumptions = []
  assume = assumptions.append

  assume("We're assuming the current year is %d."% current_year)

  pubyear = edition.publish_year
  if pubyear is None:
    pubyear = current_year
    assume("The publication year is unspecified, so we're assuming that the year of publication is %d."% pubyear)
  else:
    assume("We're assuming the year of publication is %d."% pubyear)

  if len(edition.authors) > 0:
    assume("We're assuming the list of authors is complete.")
  else:
    assume("We're assuming the authorship is anonymous.")

  maxauthordeath = None
      
  def y(author, attr):
    """Extract attribute (i.e. a string-valued date field) from author and
    convert it to integer.  If field is absent or no valid conversion, return None."""
    r = author.get(attr, None)
    try:
      return int(r)
    except (ValueError, AttributeError, TypeError):
      return None

  for author in edition.authors:
    ydeath, ybirth = y(author, 'death_date'), y(author, 'birth_date')
    aname = author.name

    death_year = None
    if aname == 'Crown':
      """We don't set death_year for Crown authorship because items with sole Crown authorship will default to pdyear = death_year + 50,
      and items with joint Crown and non-Crown authorship are determined by the other authors' information."""
      assume("We're assuming this item is under Crown copyright. Non-Crown authors, if any, render this irrelevant.")
    else:
      if ydeath:
        death_year = ydeath
        assume("We're assuming the author died in %d." % ydeath)
      elif ybirth:
        death_year = ybirth + OLDEST_PERSON_EVER_IN_CANADA
        assume("We're assuming the author was born in %d." % ybirth)
      elif pubyear:
        death_year = pubyear + OLDEST_PERSON_EVER_IN_CANADA
        assume("We're assuming the author was born at the time of publication, since we don't have a known birthdate.")

    if death_year is not None and ydeath is None:
      if death_year < current_year:
        assume("We're assuming the author didn't live longer than the oldest person ever in Canada, \
and therefore died no later than the year %d, since we have no known death date." % death_year)
      else:
        assume("We're assuming the author will live to age %d, the same as the oldest person ever in Canada so far." % OLDEST_PERSON_EVER_IN_CANADA)

    maxauthordeath = mmax(maxauthordeath, death_year)

  if maxauthordeath:
    if maxauthordeath < pubyear and pubyear < 1999:
      pdyear = pubyear + 50            
    else:
      pdyear = maxauthordeath + 50
  else:
    pdyear = pubyear + 50

  def nominal_death(author):
    ydeath, ybirth = y(author, 'death_date'), y(author, 'birth_date')
    if ydeath is not None:
      return ydeath
    if ybirth is not None:
      return ybirth + OLDEST_PERSON_EVER_IN_CANADA
    return None

  if any(nominal_death(author) is None for author in edition.authors):
    assume("We're assuming that the authors whose death dates are missing didn't die after those whose are available.")

  # assume(repr({ 'date': pdyear, 'assumptions': assumptions })) # debugging diagnostic @@
  return { 'date': pdyear, 'assumptions': assumptions }

if __name__ == '__main__':
  import doctest
  doctest.testmod()
  
