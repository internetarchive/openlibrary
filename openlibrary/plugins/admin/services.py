"""
Contains stuff needed to list services and modules run by OpenLibrary
for the admin panel
"""


class Service(object):
    """
    An OpenLibrary service with all the stuff that we need to
    manipulate it.
    """

    def __init__(self, node, name, logs = False):
        self.node = node
        self.name = name
        self.logs = logs

    def __repr__(self):
        return "Service(name = '%s', node = '%s', logs = '%s')"%(self.name, self.node, self.logs)
    

def load_all(config):
    """Loads all services specified in the config dictionary and returns
    the list of Service"""
    for node in config:
        for service in config[node].get('services',[]):
            yield Service(node = node, name = service)

