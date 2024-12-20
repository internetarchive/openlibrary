"""
Contains stuff needed to list services and modules run by OpenLibrary
for the admin panel
"""

import re
from collections import defaultdict

import requests
from bs4 import BeautifulSoup


class Nagios:
    def __init__(self, url):
        try:
            self.data = BeautifulSoup(requests.get(url).content, "lxml")
        except Exception as m:
            print(m)
            self.data = None

    def get_service_status(self, service):
        "Returns the stats of the service `service`"
        if not self.data:
            return "error-api"
        # The service name is kept inside a bunch of nested nodes We
        # walk up the nodes to find the enclosing <tr> that contains
        # the service in question. A single step is not enough since
        # there are nested tables in the layout.
        service = self.data.find(text=re.compile(service))
        if service:
            service_tr = service.findParents("tr")[2]
            status_td = service_tr.find(
                "td",
                attrs={
                    "class": re.compile(r"status(OK|RECOVERY|UNKNOWN|WARNING|CRITICAL)")
                },
            )
            return status_td['class'].replace("status", "")
        else:
            return "error-nosuchservice"


class Service:
    """
    An OpenLibrary service with all the stuff that we need to
    manipulate it.
    """

    def __init__(self, node, name, nagios, logs=False):
        self.node = node
        self.name = name
        self.logs = logs
        self.status = "Service status(TBD)"
        self.nagios = nagios.get_service_status(name)

    def __repr__(self):
        return (
            f"Service(name = '{self.name}', node = '{self.node}', logs = '{self.logs}')"
        )


def load_all(config, nagios_url):
    """Loads all services specified in the config dictionary and returns
    the list of Service"""
    d = defaultdict(list)
    nagios = Nagios(nagios_url)
    for node in config:
        services = config[node].get('services', [])
        if services:
            for service in services:
                d[node].append(Service(node=node, name=service, nagios=nagios))
    return d
