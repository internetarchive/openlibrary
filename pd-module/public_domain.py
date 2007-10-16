import os

# Dictionary of country public domain test modules
_countries = {}

# Load all country modules
def _load_countries(dummy, directory, files):
  for child in files:
    name = os.path.splitext(child)[0]
    ext = os.path.splitext(child)[1]
    if child.startswith('public_domain_') and '.py' == ext and os.path.isfile(directory + '/' + child):
      assert len(name) > 2
      try:
        _countries[name[-2:]] = __import__(os.path.splitext(child)[0])
      except NotImplementedError:
        pass
os.path.walk("./", _load_countries, None)

# Walk through country-level public domain tests
def is_public_domain(edition):
  results = {}
  for country_code, country_module in _countries.iteritems():
    results[country_code] = country_module.is_public_domain(edition)
  return results
