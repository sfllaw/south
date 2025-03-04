
import unittest
from django.conf import settings
from south.hacks import hacks

# Note: the individual test files are imported below this.

class Monkeypatcher(unittest.TestCase):

    """
    Base test class for tests that play with the INSTALLED_APPS setting at runtime.
    """

    def create_fake_app(self, name):
        
        class Fake:
            pass
        
        fake = Fake()
        fake.__name__ = name
        try:
            fake.migrations = __import__(name + ".migrations", {}, {}, ['migrations'])
        except ImportError:
            pass
        return fake


    def setUp(self):
        """
        Changes the Django environment so we can run tests against our test apps.
        """
        hacks.set_installed_apps(self.installed_apps)
    
    
    def tearDown(self):
        """
        Undoes what setUp did.
        """
        hacks.reset_installed_apps()


# Try importing all tests if asked for (then we can run 'em)
try:
    skiptest = settings.SKIP_SOUTH_TESTS
except:
    skiptest = False

if not skiptest:
    from south.tests.db import *
    from south.tests.logic import *
    from south.tests.autodetection import *
