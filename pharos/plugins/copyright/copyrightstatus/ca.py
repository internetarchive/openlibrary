OLDEST_PERSON_EVER_IN_CANADA = 117

def copyright_status(edition):
  pubyear = edition.publish_year
  assumptions = ["We're assuming the year of publication is %d."% pubyear]
  assumptions.append("We're assuming that the data is correct.")
  maxauthordeath = None
  for author in edition.authors:
    death_year = None
    if author.get('death_year'):
      death_year = author.death_year
    elif author.get('birth_year'):
      death_year = author.birth_year + OLDEST_PERSON_EVER_IN_CANADA
    elif pubyear:
      death_year = pubyear + OLDEST_PERSON_EVER_IN_CANADA
    if death_year:
      if not maxauthordeath or death_year > maxauthordeath:
        maxauthordeath = death_year
    else:
      assumptions.append("We're assuming that the author whose death dates are missing didn't die after those whose are available.")
  if maxauthordeath:
    if maxauthordeath > pubyear and pubyear < 1999:
      pdyear = pubyear + 50            
    else:
      pdyear = maxauthordeath + 75
  else:
    pdyear = pubyear + 50
  return { 'date': pdyear, 'assumptions': assumptions }
