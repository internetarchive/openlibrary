# A quick start for OpenLibrary's developers

## :: Setting up a dev instance

- First you need to have installed [Virtualbox](https://www.virtualbox.org/) and [Vagrant](https://www.vagrantup.com/).

- Fork the [OpenLibrary repo](https://github.com/internetarchive/openlibrary) to your own [Github](https://www.github.com) account.

- Clone your forked repo to your local machine:

        git clone git@github.com:YOURACCOUNT/openlibrary.git

- Switch into the directory that you just cloned:

        cd openlibrary

- Start up the dev virtual machine instance using vagrant:

        vagrant up

- You can now view your running instance by loading localhost:8080 in a web browser.

- You can log into the OpenLibrary instance as an admin, with the username *openlibrary*, password *openlibrary*.

- If you need to ssh into the vagrant dev virtual machine, type:

        vagrant ssh

- You can turn on the virtual machine using:

        vagrant halt

- Remember that, thanks to vagrant and virtual box, your local folder ```openlibrary``` (where you runned ```vagrant up```) contains *exactly* the same files as ```/openlibrary``` in the dev virtual machine (the one that you login doing ```vagrant ssh```).

## :: Administration

- If you want to add a new user to the admin group, you can do that at ```http://localhost:8080/usergroup/admin```

- The admin interface is available at ```http://localhost:8080/admin```

## :: Creating users
- If you create a user, you will have to verify the email address, but you will not be able to send email from your vagrant dev instance. Instead, you can find the verification link in the app server log, which should be in ```/var/log/upstart/ol-web.log```.

    The verification link should look like:

        http://localhost:8080/account/verify/bdc41d12bd734b27bf1522233dde03b2

    The hash you see will be different that above. Just load that link and the user will be created in your dev instance.


## :: Copying documents
- You can copy test data from the live openlibrary.org site into your dev instance. ```vagrant ssh``` into your dev instance, and run the ```copydocs.py``` script in ```/openlibrary/scripts```. If you want to add a book, you must first copy an author record, then the work record, and then the book record.

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

## :: Routing and templates
- OpenLibrary is rendered using [Templetor](http://webpy.org/docs/0.3/templetor) templates, part of the [web.py](http://webpy.org/) framework.

- The repository you cloned on your local machine is mounted at /openlibrary in the vagrant virtual machine. If you make template changes to files locally, the OpenLibrary instance in the virtual machine should automatically pick up those changes.

- The home page is rendered by [templates/home/index.html](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/templates/home/index.html), and its controller is [plugins/openlibrary/home.py](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/plugins/openlibrary/home.py#L18).

- A books page is rendered by [templates/type/edition/view.html](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/templates/type/edition/view.html). An edition is defined by edition.type. Note that editions have are served by a ```/books/OL\d+M``` url.

- A works page is rendered by ```templates/view/work/view.html```. A work is defined by work type.

## :: Memcache
- Infobase queries get cached in memcache. In the vagrant dev instance, there is a single-node memcache cluster that you can test by connecting to your test instance using ```vagrant ssh``` and then typing:

        $ cd /openlibrary
        $ python
        Python 2.7.6 (default, Mar 22 2014, 22:59:56)
        [GCC 4.8.2] on linux2
        Type "help", "copyright", "credits" or "license" for more information.
        import yaml
        from openlibrary.utils import olmemcache
        y = yaml.safe_load(open('/openlibrary/conf/openlibrary.yml'))
        c = olmemcache.Client(y['memcache_servers'])
        c.get('/authors/OL18319A')
        '{"bio": {"type": "/type/text", "value": "Mark Twain, was an American author and humorist. Twain is noted for his novels Adventures of Huckleberry Finn (1884), which has been called \\"the Great American Novel\\", and The Adventures of Tom Sawyer (1876). He is extensively quoted. Twain was a friend to presidents, artists, industrialists, and European royalty. ([Source][1].)\\r\\n\\r\\n[1]:http://en.wikipedia.org/wiki/Mark_Twain"}, "photograph": "/static/files//697/OL2622189A_photograph_1212404607766697.jpg", "name": "Mark Twain", "marc": ["1 \\u001faTwain, Mark,\\u001fd1835-1910.\\u001e"], "alternate_names": ["Mark TWAIN", "M. Twain", "TWAIN", "Twain", "Twain, Mark (pseud)", "Twain, Mark (Spirit)", "Twain, Mark, 1835-1910", "Mark (Samuel L. Clemens) Twain", "Samuel Langhorne Clemens (Mark Twain)", "Samuel Langhorne Clemens", "mark twain "], "death_date": "21 April 1910", "wikipedia": "http://en.wikipedia.org/wiki/Mark_Twain", "created": {"type": "/type/datetime", "value": "2013-03-28T07:50:47.897206"}, "last_modified": {"type": "/type/datetime", "value": "2013-03-28T07:50:47.897206"}, "latest_revision": 1, "key": "/authors/OL18319A", "birth_date": "30 November 1835", "title": "(pseud)", "personal_name": "Mark Twain", "type": {"key": "/type/author"}, "revision": 1}'

## :: Logs
- Logs for the upstart services will be in ```/var/log/upstart/```. The app server logs will be in ```/var/log/upstart/ol-web.log```
