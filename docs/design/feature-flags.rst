Feature Flags
=============

Feature flags is a way to have features under development live on production and visible only to admins/beta-users.

The idea of Feature Flags came from Flicker. They manage their development on a single branch using feature flags.

http://code.flickr.com/blog/2009/12/02/flipping-out/

Using Feature Flags
-------------------

Feature flags are used in templates and in controller classes.

To make some part of the template visible only if a feature-flag is enabled::

    $if "lists" in ctx.features:
        <h3>Lists</h3>
        $for list in page.get_lists():
            ...
            
To enable a url only if a feature flag is enabled::

    class home(delegate.page):
        path = "/"
        
        def is_enabled(self):
            return "home-v2" in web.ctx.features
        
        def GET(self):
            return render_template("home")
            

Setting Feature Flags
---------------------

In Open Library, the feature flags are specified in the ``openlibrary.yml`` file as follows::

    features:
        merge-authors: enabled
        lists: admin
        lending_v2: 
            filter: usergroup
            usergroup: beta-users

The value of a feature flag is called a *filter*. A filter can be specified either as its name or as a dict containing its name and parameters. 
For example, the following 2 example mean the same. ::

    features: 
        lists: admin
        
    features:
        lists:
            filter: admin

Available filters are:

**enabled**

    Enabled for all users.

**disabled**

    Disabled for all users.

**loggedin**

    Enabled only for logged-in users.

**admin**

    Enabled for admin users.
    
**usergroup**

    Enabled for the users part of the specified usergroup. ::
    
        lending_v2: 
            filter: usergroup
            usergroup: beta-users
    
**queryparam**

    Enabled only if the url has a specified query parameter. ::
    
        debug:
            filter: queryparam
            name: debug
            value: true
