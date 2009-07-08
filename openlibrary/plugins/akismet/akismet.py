# Version 0.1.5
# 2006/02/05

# Copyright Michael Foord 2005 - 2007
# akismet.py
# Python interface to the akismet API

# http://www.voidspace.org.uk/python/modules.shtml
# http://akismet.com

# Released subject to the BSD License
# Please see http://www.voidspace.org.uk/python/license.shtml

# For information about bugfixes, updates and support, please join the Pythonutils mailing list.
# http://groups.google.com/group/pythonutils/
# Comments, suggestions and bug reports welcome.
# Scripts maintained at http://www.voidspace.org.uk/python/index.shtml
# E-mail fuzzyman@voidspace.org.uk

"""
A python interface to the `Akismet <http://akismet.com>`_ 
{acro;API;Application Programmers Interface}. This is a web service for
blocking SPAM comments to blogs - or other online services.

You will need a Wordpress API key, from `wordpress.com <http://wordpress.com>`_.

You should pass in the keyword argument 'agent' to the name of your program,
when you create an Akismet instance. This sets the ``user-agent`` to a useful
value.

The default is : ::

    Python Interface by Fuzzyman | akismet.py/0.1.3

Whatever you pass in, will replace the *Python Interface by Fuzzyman* part.
**0.1.2** will change with the version of this interface.

"""
import os, sys
import urllib2
from urllib import urlencode

import socket
if hasattr(socket, 'setdefaulttimeout'):
    # Set the default timeout on sockets to 5 seconds
    socket.setdefaulttimeout(5)

isfile = os.path.isfile

__version__ = '0.1.5'

__all__ = (
    '__version__',
    'Akismet',
    'AkismetError',
    'APIKeyError',
    )

__author__ = 'Michael Foord <fuzzyman AT voidspace DOT org DOT uk>'

__docformat__ = "restructuredtext en"

user_agent = "%s | akismet.py/%s"
DEFAULTAGENT = 'Python Interface by Fuzzyman/%s'

class AkismetError(Exception):
    """Base class for all akismet exceptions."""

class APIKeyError(AkismetError):
    """Invalid API key."""

class Akismet(object):
    """A class for working with the akismet API"""

    baseurl = 'rest.akismet.com/1.1/'

    def __init__(self, key=None, blog_url=None, agent=None):
        """Automatically calls ``setAPIKey``."""
        if agent is None:
            agent = DEFAULTAGENT % __version__
        self.user_agent = user_agent % (agent, __version__)
        self.setAPIKey(key, blog_url)


    def _getURL(self):
        """
        Fetch the url to make requests to.
        
        This comprises of api key plus the baseurl.
        """
        return 'http://%s.%s' % (self.key, self.baseurl)
    
    
    def _safeRequest(self, url, data, headers):
        print "_safeRequest", url
        try:
            req = urllib2.Request(url, data, headers)
            h = urllib2.urlopen(req)
            resp = h.read()
        except (urllib2.HTTPError, urllib2.URLError, IOError), e:
            raise AkismetError(str(e))       
        return resp


    def setAPIKey(self, key=None, blog_url=None):
        """
        Set the wordpress API key for all transactions.
        
        If you don't specify an explicit API ``key`` and ``blog_url`` it will
        attempt to load them from a file called ``apikey.txt`` in the current
        directory.
        
        This method is *usually* called automatically when you create a new
        ``Akismet`` instance.
        """
        if key is None and isfile('apikey.txt'):
            the_file = [l.strip() for l in open('apikey.txt').readlines()
                if l.strip() and not l.strip().startswith('#')]
            try:
                self.key = the_file[0]
                self.blog_url = the_file[1]
            except IndexError:
                raise APIKeyError("Your 'apikey.txt' is invalid.")
        else:
            self.key = key
            self.blog_url = blog_url


    def verify_key(self):
        """
        This equates to the ``verify-key`` call against the akismet API.
        
        It returns ``True`` if the key is valid.
        
        The docs state that you *ought* to call this at the start of the
        transaction.
        
        It raises ``APIKeyError`` if you have not yet set an API key.
        
        If the connection to akismet fails, it allows the normal ``HTTPError``
        or ``URLError`` to be raised.
        (*akismet.py* uses `urllib2 <http://docs.python.org/lib/module-urllib2.html>`_)
        """
        if self.key is None:
            raise APIKeyError("Your have not set an API key.")
        data = { 'key': self.key, 'blog': self.blog_url }
        # this function *doesn't* use the key as part of the URL
        url = 'http://%sverify-key' % self.baseurl
        # we *don't* trap the error here
        # so if akismet is down it will raise an HTTPError or URLError
        headers = {'User-Agent' : self.user_agent}
        resp = self._safeRequest(url, urlencode(data), headers)
        if resp.lower() == 'valid':
            return True
        else:
            return False

    def _build_data(self, comment, data):
        """
        This function builds the data structure required by ``comment_check``,
        ``submit_spam``, and ``submit_ham``.
        
        It modifies the ``data`` dictionary you give it in place. (and so
        doesn't return anything)
        
        It raises an ``AkismetError`` if the user IP or user-agent can't be
        worked out.
        """
        data['comment_content'] = comment
        if not 'user_ip' in data:
            try:
                val = os.environ['REMOTE_ADDR']
            except KeyError:
                raise AkismetError("No 'user_ip' supplied")
            data['user_ip'] = val
        if not 'user_agent' in data:
            try:
                val = os.environ['HTTP_USER_AGENT']
            except KeyError:
                raise AkismetError("No 'user_agent' supplied")
            data['user_agent'] = val
        #
        data.setdefault('referrer', os.environ.get('HTTP_REFERER', 'unknown'))
        data.setdefault('permalink', '')
        data.setdefault('comment_type', 'comment')
        data.setdefault('comment_author', '')
        data.setdefault('comment_author_email', '')
        data.setdefault('comment_author_url', '')
        data.setdefault('SERVER_ADDR', os.environ.get('SERVER_ADDR', ''))
        data.setdefault('SERVER_ADMIN', os.environ.get('SERVER_ADMIN', ''))
        data.setdefault('SERVER_NAME', os.environ.get('SERVER_NAME', ''))
        data.setdefault('SERVER_PORT', os.environ.get('SERVER_PORT', ''))
        data.setdefault('SERVER_SIGNATURE', os.environ.get('SERVER_SIGNATURE',
            ''))
        data.setdefault('SERVER_SOFTWARE', os.environ.get('SERVER_SOFTWARE',
            ''))
        data.setdefault('HTTP_ACCEPT', os.environ.get('HTTP_ACCEPT', ''))
        data.setdefault('blog', self.blog_url)


    def comment_check(self, comment, data=None, build_data=True, DEBUG=False):
        """
        This is the function that checks comments.
        
        It returns ``True`` for spam and ``False`` for ham.
        
        If you set ``DEBUG=True`` then it will return the text of the response,
        instead of the ``True`` or ``False`` object.
        
        It raises ``APIKeyError`` if you have not yet set an API key.
        
        If the connection to Akismet fails then the ``HTTPError`` or
        ``URLError`` will be propogated.
        
        As a minimum it requires the body of the comment. This is the
        ``comment`` argument.
        
        Akismet requires some other arguments, and allows some optional ones.
        The more information you give it, the more likely it is to be able to
        make an accurate diagnosise.
        
        You supply these values using a mapping object (dictionary) as the
        ``data`` argument.
        
        If ``build_data`` is ``True`` (the default), then *akismet.py* will
        attempt to fill in as much information as possible, using default
        values where necessary. This is particularly useful for programs
        running in a {acro;CGI} environment. A lot of useful information
        can be supplied from evironment variables (``os.environ``). See below.
        
        You *only* need supply values for which you don't want defaults filled
        in for. All values must be strings.
        
        There are a few required values. If they are not supplied, and
        defaults can't be worked out, then an ``AkismetError`` is raised.
        
        If you set ``build_data=False`` and a required value is missing an
        ``AkismetError`` will also be raised.
        
        The normal values (and defaults) are as follows : ::
        
            'user_ip':          os.environ['REMOTE_ADDR']       (*)
            'user_agent':       os.environ['HTTP_USER_AGENT']   (*)
            'referrer':         os.environ.get('HTTP_REFERER', 'unknown') [#]_
            'permalink':        ''
            'comment_type':     'comment' [#]_
            'comment_author':   ''
            'comment_author_email': ''
            'comment_author_url': ''
            'SERVER_ADDR':      os.environ.get('SERVER_ADDR', '')
            'SERVER_ADMIN':     os.environ.get('SERVER_ADMIN', '')
            'SERVER_NAME':      os.environ.get('SERVER_NAME', '')
            'SERVER_PORT':      os.environ.get('SERVER_PORT', '')
            'SERVER_SIGNATURE': os.environ.get('SERVER_SIGNATURE', '')
            'SERVER_SOFTWARE':  os.environ.get('SERVER_SOFTWARE', '')
            'HTTP_ACCEPT':      os.environ.get('HTTP_ACCEPT', '')
        
        (*) Required values
        
        You may supply as many additional 'HTTP_*' type values as you wish.
        These should correspond to the http headers sent with the request.
        
        .. [#] Note the spelling "referrer". This is a required value by the
            akismet api - however, referrer information is not always
            supplied by the browser or server. In fact the HTTP protocol
            forbids relying on referrer information for functionality in 
            programs.
        .. [#] The `API docs <http://akismet.com/development/api/>`_ state that this value
            can be " *blank, comment, trackback, pingback, or a made up value*
            *like 'registration'* ".
        """
        if self.key is None:
            raise APIKeyError("Your have not set an API key.")
        if data is None:
            data = {}
        if build_data:
            self._build_data(comment, data)
        url = '%scomment-check' % self._getURL()
        # we *don't* trap the error here
        # so if akismet is down it will raise an HTTPError or URLError
        headers = {'User-Agent' : self.user_agent}
        resp = self._safeRequest(url, urlencode(data), headers)
        if DEBUG:
            return resp
        resp = resp.lower()
        if resp == 'true':
            return True
        elif resp == 'false':
            return False
        else:
            # NOTE: Happens when you get a 'howdy wilbur' response !
            raise AkismetError('missing required argument.')


    def submit_spam(self, comment, data=None, build_data=True):
        """
        This function is used to tell akismet that a comment it marked as ham,
        is really spam.
        
        It takes all the same arguments as ``comment_check``, except for
        *DEBUG*.
        """
        if self.key is None:
            raise APIKeyError("Your have not set an API key.")
        if data is None:
            data = {}
        if build_data:
            self._build_data(comment, data)
        url = '%ssubmit-spam' % self._getURL()
        # we *don't* trap the error here
        # so if akismet is down it will raise an HTTPError or URLError
        headers = {'User-Agent' : self.user_agent}
        self._safeRequest(url, urlencode(data), headers)


    def submit_ham(self, comment, data=None, build_data=True):
        """
        This function is used to tell akismet that a comment it marked as spam,
        is really ham.
        
        It takes all the same arguments as ``comment_check``, except for
        *DEBUG*.
        """
        if self.key is None:
            raise APIKeyError("Your have not set an API key.")
        if data is None:
            data = {}
        if build_data:
            self._build_data(comment, data)
        url = '%ssubmit-ham' % self._getURL()
        # we *don't* trap the error here
        # so if akismet is down it will raise an HTTPError or URLError
        headers = {'User-Agent' : self.user_agent}
        self._safeRequest(url, urlencode(data), headers)

"""

USAGE
=====

.. raw:: html

    {+coloring}
    
    api = Akismet(agent='Test Script')
    # if apikey.txt is in place,
    # the key will automatically be set
    # or you can call ``api.setAPIKey()``
    #
    if api.key is None:
        print "No 'apikey.txt' file."
    elif not api.verify_key():
        print "The API key is invalid."
    else:
        # data should be a dictionary of values
        # They can all be filled in with defaults
        # from a CGI environment
        if api.comment_check(comment, data):
            print 'This comment is spam.'
        else:
            print 'This comment is ham.'
    
    {-coloring}

TODO
====

Make the timeout adjustable ?

Should we fill in a default value for permalink ?

What about automatically filling in the 'HTTP_*' values from os.environ ?

"""
