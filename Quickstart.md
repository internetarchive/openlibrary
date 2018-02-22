# A quick start for OpenLibrary's developers

## Table of Contents

   - [Using the Open Library Website](#using-the-open-library-website)
     - [Logging In (As Admin)](#logging-in)
     - [Admin Interface](#admin-interface)
     - [Creating Users](#creating-users)
     - [Lending & Borrowing](#lending-and-borrowing)
   - [Importing Test Data](#importing-test-data)
   - [Frontend Developer's Guide](#frontend-guide)
     - [Building CSS and JS](#building-css-and-js)
     - [Routing & Templates](#routing-and-templates)
   - [Backend Developer's Guide](#backend-guide)
     - [Memcache](#memcache)
     - [Log Files](#logs)
     - [Database](#database)
     - [reCAPTCHA v2](#recaptcha)

## Using the Open Library Website

### Logging In

You can log into the OpenLibrary instance as an admin, with the username *openlibrary@example.com*, password *openlibrary*

### Admin Interface

For users with sufficient privileges, an admin interface is available at `http://localhost:8080/admin`.

- If you want to add a new user to the admin group, you can do that at `http://localhost:8080/usergroup/admin`

### Creating Users

- If you create a user, you will have to verify the email address, but you will not be able to send email from your vagrant dev instance. Instead, you can find the verification link in the app server log, which should be in `/var/log/upstart/ol-web.log`.

    The verification link should look like:

        http://localhost:8080/account/verify/bdc41d12bd734b27bf1522233dde03b2

    The hash you see will be different that above. Just load that link and the user will be created in your dev instance.

Debugging: During sign up, if you get an error "INPUT ERROR: K: FORMAT OF SITE KEY WAS INVALID", then it probably means reCAPTCHA has not been set up on your local dev environment. See "reCAPTCHA" below.

### Lending and Borrowing

These instructions are fairly specific to Internet Archive staff who
are administrating the Open Library service and who have access to the
production olsystem repository.

It essentially enables your local developer repository to behave as if
it were actually openlibrary.org, and thus sync with and to
openlibrary.org's loans:

[Enabling Lending on Localhost](https://github.com/internetarchive/olsystem/blob/master/Readme.md#enabling-lending-on-localhost)

## Importing Test Data

You can copy test data from the live openlibrary.org site into your dev instance. `vagrant ssh` into your dev instance, and run the `copydocs.py` script in `/openlibrary/scripts`. If you want to add a book, you must first copy an author record, then the work record, and then the book record.

        $ cd /openlibrary/scripts

        vagrant@ol-dev:/openlibrary/scripts$ $ ./copydocs.py /authors/OL1385865A
            fetching ['/authors/OL1385865A']
            saving ['/authors/OL1385865A']
            [{'key': '/authors/OL1385865A', 'revision': 1}]

        vagrant@ol-dev:/openlibrary/scripts$ ./copydocs.py /works/OL14906539W
            fetching ['/works/OL14906539W']
            saving ['/works/OL14906539W']
            [{'key': '/works/OL14906539W', 'revision': 1}]

        vagrant@ol-dev:/openlibrary/scripts$ ./copydocs.py /books/OL24966433M
            fetching ['/books/OL24966433M']
            saving ['/books/OL24966433M']
            [{'key': '/books/OL24966433M', 'revision': 1}]


## Frontend Guide

### Building CSS and JS

In local development, after making changes to CSS or JS, make sure to run `make css` or `make js`, in order to re-compile the build/ static assets. You might also need to restart the webserver and/or clear browser caches to see the changes.

### Routing and Templates

- OpenLibrary is rendered using [Templetor](http://webpy.org/docs/0.3/templetor) templates, part of the [web.py](http://webpy.org/) framework.

- The repository you cloned on your local machine is mounted at /openlibrary in the vagrant virtual machine. If you make template changes to files locally, the OpenLibrary instance in the virtual machine should automatically pick up those changes.

- The home page is rendered by [templates/home/index.html](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/templates/home/index.html), and its controller is [plugins/openlibrary/home.py](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/plugins/openlibrary/home.py#L18).

- A books page is rendered by [templates/type/edition/view.html](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/templates/type/edition/view.html). An edition is defined by edition.type. Note that editions have are served by a `/books/OL\d+M` url.

- A works page is rendered by `templates/view/work/view.html`. A work is defined by work type.

## Backend Guide

### Memcache

- Infobase queries get cached in memcache. In the vagrant dev instance, there is a single-node memcache cluster that you can test by connecting to your test instance using `vagrant ssh` and then typing:

        $ cd /openlibrary
        $ python
        Python 2.7.6 (default, Mar 22 2014, 22:59:56)
        [GCC 4.8.2] on linux2
        Type "help", "copyright", "credits" or "license" for more information.
        >>> import yaml
        >>> from openlibrary.utils import olmemcache
        >>> y = yaml.safe_load(open('/openlibrary/conf/openlibrary.yml'))
        >>> mc = olmemcache.Client(y['memcache_servers'])

  to **GET** the memcached entry:

        >>> mc.get('/authors/OL18319A')
        '{"bio": {"type": "/type/text", "value": "Mark Twain, was an American author and humorist. Twain is noted for his novels Adventures of Huckleberry Finn (1884), which has been called \\"the Great American Novel\\", and The Adventures of Tom Sawyer (1876). He is extensively quoted. Twain was a friend to presidents, artists, industrialists, and European royalty. ([Source][1].)\\r\\n\\r\\n[1]:http://en.wikipedia.org/wiki/Mark_Twain"}, "photograph": "/static/files//697/OL2622189A_photograph_1212404607766697.jpg", "name": "Mark Twain", "marc": ["1 \\u001faTwain, Mark,\\u001fd1835-1910.\\u001e"], "alternate_names": ["Mark TWAIN", "M. Twain", "TWAIN", "Twain", "Twain, Mark (pseud)", "Twain, Mark (Spirit)", "Twain, Mark, 1835-1910", "Mark (Samuel L. Clemens) Twain", "Samuel Langhorne Clemens (Mark Twain)", "Samuel Langhorne Clemens", "mark twain "], "death_date": "21 April 1910", "wikipedia": "http://en.wikipedia.org/wiki/Mark_Twain", "created": {"type": "/type/datetime", "value": "2013-03-28T07:50:47.897206"}, "last_modified": {"type": "/type/datetime", "value": "2013-03-28T07:50:47.897206"}, "latest_revision": 1, "key": "/authors/OL18319A", "birth_date": "30 November 1835", "title": "(pseud)", "personal_name": "Mark Twain", "type": {"key": "/type/author"}, "revision": 1}'

  to **DELETE** a memcached entry:

        >>> mc.delete('/authors/OL18319A')

- You can also find memcached items using the Internet Archive ID (import `memcache` instead of `olmemecache`):

        >>> import yaml
        >>> import memcache
        >>> y = yaml.safe_load(open('openlibrary.yml'))
        >>> mc = memcache.Client(y['memcache_servers'])

        >>> mc.get('ia.get_metadata-"houseofscorpion00farmrich"')

### Logs

- Logs for the upstart services will be in `/var/log/upstart/`.

- The app server logs will be in `/var/log/upstart/ol-web.log`.


### Database

- You should never work directly with the database, all the data are indeed managed by OpenLibrary through *infobase*, but, if you are brave and curious, here you can find some useful infos.

- The first thing you have to know is that OpenLibrary is based on a [triplestore](https://en.wikipedia.org/wiki/Triplestore) database running on *Postgres*.

- To connect to the db run:

              psql openlibrary

- All the OL’s entities are stored as things in the `thing` table.
Every raw contains:

              id | key | type | latest_revision | created | last_modified
              ---+-----+------+-----------------+---------+---------------

- It is useful identify the `id` of some particular types: `/type/author` `/type/work` `/type/edition` `/type/user`

             openlibrary=# SELECT * FROM thing WHERE key='/type/author' OR key='/type/edition' OR key='/type/work' OR key='/type/user';

  this query returns something like:

         id       |      key      | type | latest_revision |          created           |       last_modified
         ---------+---------------+------+-----------------+----------------------------+----------------------------
         17872418 | /type/work    |    1 |              14 | 2008-08-18 22:51:38.685066 | 2010-08-09 23:37:25.678493
         22       | /type/user    |    1 |               5 | 2008-03-19 16:44:20.354477 | 2009-03-16 06:21:53.030443
         52       | /type/edition |    1 |              33 | 2008-03-19 16:44:24.216334 | 2009-09-22 10:44:06.178888
         58       | /type/author  |    1 |              11 | 2008-03-19 16:44:24.216334 | 2009-06-29 12:35:31.346997

    - to count the **authors**:

              openlibrary=# SELECT count(*) as count FROM thing WHERE type='58';

    - to count the **works**:

              openlibrary=# SELECT count(*) as count FROM thing WHERE type='17872418';

    - to count the **editions**:

              openlibrary=# SELECT count(*) as count FROM thing WHERE type='52';

    - to count the **users**:

              openlibrary=# SELECT count(*) as count FROM thing WHERE type='22';


### Recaptcha

- Currently we use reCAPTCHA v2, which validates users based on the "I'm not a robot" checkbox. 

- To develop with reCAPTCHA v2 locally, for testing new user signups and edits that require a user to prove they are human, you will need to [sign up for a reCAPTCHA API key pair](https://www.google.com/recaptcha/admin#list) from Google Developers (Google account required): `https://developers.google.com/recaptcha/docs/display`

- On the *Manage your reCAPTCHA v2 API keys* page under *Register a new site* enter the following values:

| | |
| --- | --- |
| **Label**   | *Local OL dev* |
| **Domains** | *0.0.0.0* |

- All reCAPTCHA v2 API keys work for local testing, so you do not need to enter the actual OpenLibrary domain. For example, `0.0.0.0` will work for the purpose of local development:

- Once you have generated the keys, add them to your local `conf/openlibrary.yml` file by filling in the public and private keys under the `plugin_recaptcha` section.

- From within vagrant, restart the Open Library service via /etc/init.d/ol-start. You can simply run `vagrant reload` as well for the same.

### Credits and special thanks

- [rajbot](https://github.com/rajbot)
- [gdamdam](https://github.com/gdamiola)
- [anandology](https://github.com/anandology)
- [bfalling](https://github.com/bfalling)
- [mekarpeles](https://github.com/mekarpeles)
