"""
Contains stuff needed to list services and modules run by OpenLibrary
for the admin panel
"""

from collections import defaultdict

class Service(object):
    """
    An OpenLibrary service with all the stuff that we need to
    manipulate it.
    """

    def __init__(self, node, name, logs = False):
        self.node = node
        self.name = name
        self.logs = logs
        self.status = "Service status(TBD)"
        self.nagios = "Nagios status (TBD)"

    def __repr__(self):
        return "Service(name = '%s', node = '%s', logs = '%s')"%(self.name, self.node, self.logs)
    

def load_all(config):
    """Loads all services specified in the config dictionary and returns
    the list of Service"""
    d = defaultdict(list)
    for node in config:
        services = config[node].get('services',[])
        if services:
            for service in services:
                d[node].append(Service(node = node, name = service))
    return d

