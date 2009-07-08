"""
copyrightstatus: calculate whether things are in the public domain in various countries

    >>> import copyrightstatus
    >>> copyrightstatus.is_public_domain(edition)
    {
      'ca': {
        'date': 2044, 
        'assumptions': [
          "We're assuming that the data is correct.", 
          "We're assuming that the author whose death dates are missing didn't die after those whose are available."]}, 
      'us': {
        'date': 2117, 
        'assumptions': [
          "We're assuming that the data is correct.", 
          "We're assuming it was published.", 
          "We're assuming it was published in the US.", 
          "We're assuming it was published with a valid copyright notice.", 
          "We're assuming it wasn't published by a corporation or under a psuedonym.", 
          "We're assuming that the author lived as long as the oldest person ever and published the work at birth."
        ]}
    }

`date` is the expected date it will be public domain. `assumptions` is a list
of assumptions made in calculating this.

"""

import os

import ca, us
_countries = {'ca': ca, 'us': us}

# Walk through country-level public domain tests
def copyright_status(edition):
  results = {}
  for country_code, country_module in _countries.iteritems():
    results[country_code] = country_module.copyright_status(edition)
  return results
