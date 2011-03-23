"""
Tests for the services module used by the admin interface.
"""

def test_loader(serviceconfig):
    "Make sure services are loaded"
    from .. import services
    services = services.load_all(serviceconfig)
    assert len(services) == 4
    assert services[0].node == "ol-web0" and services[0].name == "7071-ol-gunicorn"
    assert services[1].node == "ol-web0" and services[1].name == "7060-memcached"
    assert services[2].node == "ol-web1" and services[2].name == "7071-ol-gunicorn"
    assert services[3].node == "ol-web1" and services[3].name == "7060-memcached"
    
    
    
    
    
