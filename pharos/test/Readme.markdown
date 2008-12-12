# Open Library test suite

The testsuite expects a config file `~/.oltestrc~ with username and password of the test user. Here is a sample file.

    [account]
    username = testuser
    password = test123

Test the production server:
    
    $ python test/test_all.py

Test the staging server:

    $ python test/test_all.py --staging

Test your development server:

    $ python test/test_all.py --url http://0.0.0.0:8080

Test in verbose mode:

    $ python test/test_all.py -v

Test individual tests:

    $ python test/test_login.py LoginTest
    $ python test/test_login.py LoginTest.testLogin

