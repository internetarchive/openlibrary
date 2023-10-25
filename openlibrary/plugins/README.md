# Plugins

The plugins directory defines and registers all the Routers responsible for responding to requests to the Open Library website.

## Understanding Routers
In Open Library, when a patron navigates to an openlibrary.org url in their browser, the request is typically captured by a Router class which is defined by files within the `plugins/` directory. Any Router class will be responsible for doing 4 things:

1. Defining a `path` -- a regular expression pattern used to decide whether a patron's requests should be handled by this Router
2. Implementing necessary class methods (e.g. GET and POST) corresponding to the patron's HTTP request type
3. Making calls to the right data `models`
4. Prepare data to be returned (which could be e.g. a rendered template or json) -- this may include setting any headers or content-types necessary for this data

The first step is to figure out where within the `plugins/` directory your new route should live and whether it best lives in an existing file or a new file. An overview of the different plugin types are discussed in [this technical overview video](https://archive.org/embed/openlibrary-tour-2020/technical_overview.mp4?start=1017).

## Understanding Directories

The following describes what each plugin directory does, by convention, in decreasing order of presumed relevance:

* openlibrary -- most public pages meant to be read/consumed live here
  * `code.py` defines the `/isbn` endpoint and what python functions our html templates have access to!
  * `js/` is where our javascript lives
  * `api.py` is many of our APIs are defined
  * `lists.py` defines many of the routes for the List feature
* upstream -- handles incoming stateful data requests (wiki edits, uploads, adding a book, logins, etc)
  * responds to actions (e.g. borrowing) and account related requests: editing, mybooks pages, account login, settings
* worksearch -- renders our /search/* related pages and all our search querying logic.
  * `code.py` contains most of the logic and routes for `/search`, the `/barcodescanner`, '/advancedsearch`, `/search/lists`, `/search/subjects`, etc, as well as their json returning counterparts
* importapi -- defines our book import API endpoints
  * `code.py` again defines most of the core logic we care about
* admin -- our admin pages and logic
* books -- old-stype book APIs (likely not relevant)

## Code.py

Almost every `plugins/` directory defines a central `code.py` which is similar to `__init__.py` in that it contains the logic required to register its directory's plugins with the system. In addition to acting as an entry point for all the other plugins in the directory and performing setup(), it also may define its own Routers. If you're not sure where in a plugin to look for a Router, that's likely a good place to start.

## Tutorial: Implementing a new Route

There are two ways to implement a new Open Library Route. The first way is to use your discretion to add a new Route to the correct pre-existing plugin file. The second way is to create a new directory and/or file which will require an additional step of registering your plugin with Open Library. We'll only walkthrough the first case here -- for those who need to register a new plugin, please see `openlibrary/plugins/openlibrary/code.py` for an [example](https://github.com/internetarchive/openlibrary/blob/208fe9de10f24d1f54b691f4a40d1dc4b0148745/openlibrary/plugins/openlibrary/code.py#L1105-L1143).

Let's say I wanted to create a page on Open Library called `/search/many` for a search experience that lets patrons search for multiple books in bulk. The first thing I'd do is make a determination of where it should live -- likely in `worksearch/code.py`. We'd then define our Route as follows:

```
class search_many(delegate.page):
    path = '/search/many'

    def GET(self):
        i = web.input(q='')
        return render_template('search/many', q=i.q)
```

Every Router is a class that extends something like `delegate.page`. The Router will define a `GET`, `POST`, etc, as appropriate to deal with corresponding HTTP requests of that type from the patron. The function parameters defined by the GET and POST of the Router depend on and are linked to the regex pattern specified by the Router's `path`.

The following example from [plugins/openlibrary/api.py](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/plugins/openlibrary/api.py#L65-L71), The `trending_books_api` Router defines a `path` with a regex `"/trending(/?.*)"` that captures everything after `/trending/` and forwards it into the GET function as the parameter `period`. In this example, if a patron goes to `/trending/daily`, the request will match the Router's path regex and the Router will call the GET method with `period=daily` as an argument.

```
class trending_books_api(delegate.page):
    path = "/trending(/?.*)"
    # path = "/trending/(now|daily|weekly|monthly|yearly|forever)"
    encoding = "json"

    def GET(self, period="/daily"):
```

In our first example `i = web.input(q='')` is used to access the GET query parameters specified by the patron's request from the URL (e.g. if the patron queries for /search/many?q=test then `i.q` will be "test".

The final line of the Router in our example makes a call to `render_template` which will fetch the corresponding template, by name, from the `templates/` directory (specified by the 1st argument -- in this case the file "templates/search/many.html) and then pass in any of the variables this template needs to render (in this case the value `q`). The values passed in to the template must also be defined in the header of the HTML template within the `$ def with(...)` line. For more information on rendering templates, refer to the [Front-end Guide](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide#routing-and-templates) in our Github Wiki.

In order to get this example to work, you will first need to create a new file `templates/search/many.html` with the following body content:

```
$ def with (q="")

Your query was $(q)!
```

You can now restart your server and test that your application is working by going to `/search/many?q=test&debug=true`, as described in our [debugging website errors video](https://archive.org/embed/openlibrary-tour-2020/openlibrary-debugging-webpage-errors.mp4)
