"""
Contains stuff needed to list services and modules run by OpenLibrary
for the admin panel
"""


class Service(object):
    """
    An OpenLibrary service with all the stuff that we need to
    manipulate it.
    """

    def __init__(self, node, name, logs):
        self.node = node
        self.name = name
        self.logs = logs



