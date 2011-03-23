"""
Tests for the services module used by the admin interface.
"""

def test_loader(serviceconfig):
    "Make sure services are loaded"
    from .. import services
    services = services.load_all(serviceconfig)
    assert len(services.keys()) == 2
    s = sorted(services.keys())
    assert s[0] == "ol-web0"
    assert s[1] == "ol-web1"
    assert services['ol-web0'][0].name == "7071-ol-gunicorn"
    assert services['ol-web0'][1].name == "7060-memcached"
    assert services['ol-web1'][0].name == "7072-ol-gunicorn"
    assert services['ol-web1'][1].name == "7061-memcached"
    
    
    
    
    
    
    
