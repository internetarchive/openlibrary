"""Utilities for rendering Graphite graphs.
"""
import urllib
import web
from infogami import config

def get_graphite_base_url():
    return config.get("graphite_base_url", "")

class GraphiteGraph:
    """Representation of Graphite graph.
    
    Usage:
    
        g = GraphiteGraph()
        g.add("stats.timers.ol.pageload.all.mean").apply("movingAverage", 20).alias("all")
        print g.render()
    
    In templates:

        $ g = GraphiteGraph()
        $g.add("stats.timers.ol.pageload.all.mean").apply("movingAverage", 20).alias("all")
        $:g.render()
    """
    def __init__(self):
        self.series_list = []
        
    def add(self, name):
        s = Series(name)
        self.series_list.append(s)
        return s
        
    def get_queryparams(self, **options):
        """Returns query params to be passed to the image URL for rendering this graph.
        """
        options["target"] = [s.name for s in self.series_list]
        return options
        
    def render(self, **options):
        """Renders the graphs as an img tag.
        
        Usage in templates:
        
            $:g.render(yLimit=100, width=300, height=400)
        """
        return '<img src="%s/render/?%s"/>' % (get_graphite_base_url(), urllib.urlencode(self.get_queryparams(**options), doseq=True))
        
class Series:
    """One series in the GraphiteGraph.
    """
    def __init__(self, name):
        self.name = name
        
    def apply(self, funcname, *args):
        """Applies a function to this series.
        
        :return: Returns self
        """
        self.name = "%s(%s, %s)" % (funcname, self.name, ", ".join(repr(a) for a in args))
        return self
        
    def alias(self, name):
        """Shorthand for calling s.apply("alias", name)
        """
        return self.apply("alias", name)
        
    def __repr__(self):
        return "<series: %r>" % self.name
        
    def __str__(self):
        # Returning empty string to allow template use $g.add("foo") without printing anything.
        return ""
        
def setup():
    web.template.Template.globals.update({
        'GraphiteGraph': GraphiteGraph,
    })