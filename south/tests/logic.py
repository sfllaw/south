import unittest

from collections import deque
import datetime
import sys
import os
import StringIO

from south import exceptions
from south.migration import migrate_app
from south.migration.base import all_migrations, Migration, Migrations
from south.migration.utils import depends, dfs, flatten, get_app_name
from south.models import MigrationHistory
from south.tests import Monkeypatcher

# Add the tests directory so fakeapp is on sys.path
test_root = os.path.dirname(__file__)
sys.path.append(test_root)


class TestMigration(Monkeypatcher):
    installed_apps = ["fakeapp", "otherfakeapp", "brokenapp"]

    def setUp(self):
        super(TestMigration, self).setUp()
        self.fakeapp = Migrations('fakeapp')
        self.otherfakeapp = Migrations('otherfakeapp')
        self.brokenapp = Migrations('brokenapp')

    def test_str(self):
        migrations = [str(m) for m in self.fakeapp]
        self.assertEqual(['fakeapp:0001_spam',
                          'fakeapp:0002_eggs',
                          'fakeapp:0003_alter_spam'],
                         migrations)
                         
    def test_repr(self):
        migrations = [repr(m) for m in self.fakeapp]
        self.assertEqual(['<Migration: fakeapp:0001_spam>',
                          '<Migration: fakeapp:0002_eggs>',
                          '<Migration: fakeapp:0003_alter_spam>'],
                         migrations)

    def test_app_name(self):
        self.assertEqual(['fakeapp', 'fakeapp', 'fakeapp'],
                         [m.app_name() for m in self.fakeapp])
                         
    def test_name(self):
        self.assertEqual(['0001_spam', '0002_eggs', '0003_alter_spam'],
                         [m.name() for m in self.fakeapp])

    def test_full_name(self):
        self.assertEqual(['fakeapp.migrations.0001_spam',
                          'fakeapp.migrations.0002_eggs',
                          'fakeapp.migrations.0003_alter_spam'],
                         [m.full_name() for m in self.fakeapp])
    
    def test_migration(self):
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        M3 = __import__("fakeapp.migrations.0003_alter_spam", {}, {}, ['Migration']).Migration
        self.assertEqual([M1, M2, M3],
                         [m.migration().Migration for m in self.fakeapp])
        self.assertRaises(exceptions.UnknownMigration,
                          self.fakeapp['9999_unknown'].migration)

    def test_previous(self):
        self.assertEqual([None,
                          self.fakeapp['0001_spam'],
                          self.fakeapp['0002_eggs']],
                         [m.previous() for m in self.fakeapp])

    def test_dependencies(self):
        self.assertEqual([[],
                          [self.fakeapp['0001_spam']],
                          [self.fakeapp['0002_eggs']]],
                         [m.dependencies() for m in self.fakeapp])
        self.assertEqual([[self.fakeapp['0001_spam']],
                          [self.otherfakeapp['0001_first']],
                          [self.otherfakeapp['0002_second'],
                           self.fakeapp['0003_alter_spam']]],
                         [m.dependencies() for m in self.otherfakeapp])
        depends_on_unmigrated = self.brokenapp['0001_depends_on_unmigrated']
        self.assertRaises(exceptions.DependsOnUnmigratedApplication,
                          depends_on_unmigrated.dependencies)
        depends_on_unknown = self.brokenapp['0002_depends_on_unknown']
        self.assertRaises(exceptions.DependsOnUnknownMigration,
                          depends_on_unknown.dependencies)
        depends_on_higher = self.brokenapp['0003_depends_on_higher']
        self.assertRaises(exceptions.DependsOnHigherMigration,
                          depends_on_higher.dependencies)

    def test_forwards_plan(self):
        self.assertEqual([[self.fakeapp['0001_spam']],
                          [self.fakeapp['0001_spam'],
                           self.fakeapp['0002_eggs']],
                          [self.fakeapp['0001_spam'],
                           self.fakeapp['0002_eggs'],
                           self.fakeapp['0003_alter_spam']]],
                         [m.forwards_plan() for m in self.fakeapp])
        self.assertEqual([[self.fakeapp['0001_spam'],
                           self.otherfakeapp['0001_first']],
                          [self.fakeapp['0001_spam'],
                           self.otherfakeapp['0001_first'],
                           self.otherfakeapp['0002_second']],
                          [self.fakeapp['0001_spam'],
                           self.otherfakeapp['0001_first'],
                           self.otherfakeapp['0002_second'],
                           self.fakeapp['0002_eggs'],
                           self.fakeapp['0003_alter_spam'],
                           self.otherfakeapp['0003_third']]],
                         [m.forwards_plan() for m in self.otherfakeapp])

    def test_is_before(self):
        F1 = self.fakeapp['0001_spam']
        F2 = self.fakeapp['0002_eggs']
        F3 = self.fakeapp['0003_alter_spam']
        O1 = self.otherfakeapp['0001_first']
        O2 = self.otherfakeapp['0002_second']
        O3 = self.otherfakeapp['0003_third']
        self.assertTrue(F1.is_before(F2))
        self.assertTrue(F1.is_before(F3))
        self.assertTrue(F2.is_before(F3))
        self.assertEqual(O3.is_before(O1), False)
        self.assertEqual(O3.is_before(O2), False)
        self.assertEqual(O2.is_before(O2), False)
        self.assertEqual(O2.is_before(O1), False)
        self.assertEqual(F2.is_before(O1), None)
        self.assertEqual(F2.is_before(O2), None)
        self.assertEqual(F2.is_before(O3), None)


class TestMigrationDependencies(Monkeypatcher):
    installed_apps = ['deps_a', 'deps_b', 'deps_c']

    def setUp(self):
        super(TestMigrationDependencies, self).setUp()
        self.deps_a = Migrations('deps_a')
        self.deps_b = Migrations('deps_b')
        self.deps_c = Migrations('deps_c')

    def test_dependencies(self):
        self.assertEqual([[],
                          [self.deps_a['0001_a']],
                          [self.deps_a['0002_a']],
                          [self.deps_a['0003_a'],
                           self.deps_b['0003_b']],
                          [self.deps_a['0004_a']]],
                         [m.dependencies() for m in self.deps_a])
        self.assertEqual([[],
                          [self.deps_b['0001_b'],
                           self.deps_a['0002_a']],
                          [self.deps_b['0002_b'],
                           self.deps_a['0003_a']],
                          [self.deps_b['0003_b']],
                          [self.deps_b['0004_b']]],
                         [m.dependencies() for m in self.deps_b])
        self.assertEqual([[],
                          [self.deps_c['0001_c']],
                          [self.deps_c['0002_c']],
                          [self.deps_c['0003_c']],
                          [self.deps_c['0004_c'],
                           self.deps_a['0002_a']]],
                         [m.dependencies() for m in self.deps_c])

    def test_dependents(self):
        self.assertEqual([deque([self.deps_a['0002_a']]),
                          deque([self.deps_c['0005_c'],
                                 self.deps_b['0002_b'],
                                 self.deps_a['0003_a']]),
                          deque([self.deps_b['0003_b'],
                                 self.deps_a['0004_a']]),
                          deque([self.deps_a['0005_a']]),
                          deque([])],
                         [m.dependents() for m in self.deps_a])
        self.assertEqual([deque([self.deps_b['0002_b']]),
                          deque([self.deps_b['0003_b']]),
                          deque([self.deps_b['0004_b'],
                                 self.deps_a['0004_a']]),
                          deque([self.deps_b['0005_b']]),
                          deque([])],
                         [m.dependents() for m in self.deps_b])
        self.assertEqual([deque([self.deps_c['0002_c']]),
                          deque([self.deps_c['0003_c']]),
                          deque([self.deps_c['0004_c']]),
                          deque([self.deps_c['0005_c']]),
                          deque([])],
                         [m.dependents() for m in self.deps_c])

    def test_forwards_plan(self):
        self.assertEqual([[self.deps_a['0001_a']],
                          [self.deps_a['0001_a'],
                           self.deps_a['0002_a']],
                          [self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_a['0003_a']],
                          [self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_a['0003_a'],
                           self.deps_b['0001_b'],
                           self.deps_b['0002_b'],
                           self.deps_b['0003_b'],
                           self.deps_a['0004_a']],
                          [self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_a['0003_a'],
                           self.deps_b['0001_b'],
                           self.deps_b['0002_b'],
                           self.deps_b['0003_b'],
                           self.deps_a['0004_a'],
                           self.deps_a['0005_a']]],
                         [m.forwards_plan() for m in self.deps_a])
        self.assertEqual([[self.deps_b['0001_b']],
                          [self.deps_b['0001_b'],
                           self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_b['0002_b']],
                          [self.deps_b['0001_b'],
                           self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_b['0002_b'],
                           self.deps_a['0003_a'],
                           self.deps_b['0003_b']],
                          [self.deps_b['0001_b'],
                           self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_b['0002_b'],
                           self.deps_a['0003_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0004_b']],
                          [self.deps_b['0001_b'],
                           self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_b['0002_b'],
                           self.deps_a['0003_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0004_b'],
                           self.deps_b['0005_b']]],
                         [m.forwards_plan() for m in self.deps_b])
        self.assertEqual([[self.deps_c['0001_c']],
                          [self.deps_c['0001_c'],
                           self.deps_c['0002_c']],
                          [self.deps_c['0001_c'],
                           self.deps_c['0002_c'],
                           self.deps_c['0003_c']],
                          [self.deps_c['0001_c'],
                           self.deps_c['0002_c'],
                           self.deps_c['0003_c'],
                           self.deps_c['0004_c']],
                          [self.deps_c['0001_c'],
                           self.deps_c['0002_c'],
                           self.deps_c['0003_c'],
                           self.deps_c['0004_c'],
                           self.deps_a['0001_a'],
                           self.deps_a['0002_a'],
                           self.deps_c['0005_c']]],
                         [m.forwards_plan() for m in self.deps_c])

    def test_backwards_plan(self):
        self.assertEqual([[self.deps_c['0005_c'],
                           self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0002_b'],
                           self.deps_a['0003_a'],
                           self.deps_a['0002_a'],
                           self.deps_a['0001_a']],
                          [self.deps_c['0005_c'],
                           self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0002_b'],
                           self.deps_a['0003_a'],
                           self.deps_a['0002_a']],
                          [self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b'],
                           self.deps_a['0003_a']],
                          [self.deps_a['0005_a'],
                           self.deps_a['0004_a']],
                          [self.deps_a['0005_a']]],
                         [m.backwards_plan() for m in self.deps_a])
        self.assertEqual([[self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0002_b'],
                           self.deps_b['0001_b']],
                          [self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b'],
                           self.deps_b['0002_b']],
                          [self.deps_b['0005_b'],
                           self.deps_b['0004_b'],
                           self.deps_a['0005_a'],
                           self.deps_a['0004_a'],
                           self.deps_b['0003_b']],
                          [self.deps_b['0005_b'],
                           self.deps_b['0004_b']],
                          [self.deps_b['0005_b']]],
                         [m.backwards_plan() for m in self.deps_b])
        self.assertEqual([[self.deps_c['0005_c'],
                           self.deps_c['0004_c'],
                           self.deps_c['0003_c'],
                           self.deps_c['0002_c'],
                           self.deps_c['0001_c']],
                          [self.deps_c['0005_c'],
                           self.deps_c['0004_c'],
                           self.deps_c['0003_c'],
                           self.deps_c['0002_c']],
                          [self.deps_c['0005_c'],
                           self.deps_c['0004_c'],
                           self.deps_c['0003_c']],
                          [self.deps_c['0005_c'],
                           self.deps_c['0004_c']],
                          [self.deps_c['0005_c']]],
                         [m.backwards_plan() for m in self.deps_c])


class TestCircularDependencies(Monkeypatcher):
    installed_apps = ["circular_a", "circular_b"]

    def test_plans(self):
        circular_a = Migrations('circular_a')
        circular_b = Migrations('circular_b')
        self.assertRaises(exceptions.CircularDependency,
                          Migration.forwards_plan, circular_a[-1])
        self.assertRaises(exceptions.CircularDependency,
                          Migration.forwards_plan, circular_b[-1])
        self.assertRaises(exceptions.CircularDependency,
                          Migration.backwards_plan, circular_a[-1])
        self.assertRaises(exceptions.CircularDependency,
                          Migration.backwards_plan, circular_b[-1])


class TestMigrations(Monkeypatcher):
    installed_apps = ["fakeapp", "otherfakeapp"]

    def test_all(self):
        
        M1 = Migrations(__import__("fakeapp", {}, {}, ['']))
        M2 = Migrations(__import__("otherfakeapp", {}, {}, ['']))
        
        self.assertEqual(
            [M1, M2],
            list(all_migrations()),
        )

    def test(self):
        
        M1 = Migrations(__import__("fakeapp", {}, {}, ['']))
        
        self.assertEqual(M1, Migrations("fakeapp"))
        self.assertEqual(M1, Migrations(self.create_fake_app("fakeapp")))

    def test_application(self):
        fakeapp = Migrations("fakeapp")
        application = __import__("fakeapp", {}, {}, [''])
        self.assertEqual(application, fakeapp.application)

    def test_migration(self):
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        migration = Migrations('fakeapp')
        self.assertEqual(M1, migration['0001_spam'].migration().Migration)
        self.assertEqual(M2, migration['0002_eggs'].migration().Migration)
        self.assertRaises(exceptions.UnknownMigration,
                          migration['0001_jam'].migration)

    def test_guess_migration(self):
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        migration = Migrations('fakeapp')
        self.assertEqual(M1, migration.guess_migration("0001_spam").migration().Migration)
        self.assertEqual(M1, migration.guess_migration("0001_spa").migration().Migration)
        self.assertEqual(M1, migration.guess_migration("0001_sp").migration().Migration)
        self.assertEqual(M1, migration.guess_migration("0001_s").migration().Migration)
        self.assertEqual(M1, migration.guess_migration("0001_").migration().Migration)
        self.assertEqual(M1, migration.guess_migration("0001").migration().Migration)
        self.assertRaises(exceptions.UnknownMigration,
                          migration.guess_migration, "0001-spam")
        self.assertRaises(exceptions.MultiplePrefixMatches,
                          migration.guess_migration, "000")
        self.assertRaises(exceptions.MultiplePrefixMatches,
                          migration.guess_migration, "")
        self.assertRaises(exceptions.UnknownMigration,
                          migration.guess_migration, "0001_spams")
        self.assertRaises(exceptions.UnknownMigration,
                          migration.guess_migration, "0001_jam")

    def test_app_name(self):
        names = ['fakeapp', 'otherfakeapp']
        self.assertEqual(names,
                         [Migrations(n).app_name() for n in names])
    
    def test_full_name(self):
        names = ['fakeapp', 'otherfakeapp']
        self.assertEqual([n + '.migrations' for n in names],
                         [Migrations(n).full_name() for n in names])


class TestMigrationLogic(Monkeypatcher):

    """
    Tests if the various logic functions in migration actually work.
    """
    
    installed_apps = ["fakeapp", "otherfakeapp"]

    def assertListEqual(self, list1, list2):
        list1 = list(list1)
        list2 = list(list2)
        list1.sort()
        list2.sort()
        return self.assertEqual(list1, list2)

    def test_find_ghost_migrations(self):
        pass
    
    def test_apply_migrations(self):
        MigrationHistory.objects.all().delete()
        migrations = Migrations("fakeapp")
        
        # We should start with no migrations
        self.assertEqual(list(MigrationHistory.objects.all()), [])
        
        # Apply them normally
        migrate_app(migrations, target_name=None, fake=False,
                    load_initial_data=True)
        
        # We should finish with all migrations
        self.assertListEqual(
            ((u"fakeapp", u"0001_spam"),
             (u"fakeapp", u"0002_eggs"),
             (u"fakeapp", u"0003_alter_spam"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Now roll them backwards
        migrate_app(migrations, target_name="zero", fake=False)
        
        # Finish with none
        self.assertEqual(list(MigrationHistory.objects.all()), [])
    
    
    def test_migration_merge_forwards(self):
        MigrationHistory.objects.all().delete()
        migrations = Migrations("fakeapp")
        
        # We should start with no migrations
        self.assertEqual(list(MigrationHistory.objects.all()), [])
        
        # Insert one in the wrong order
        MigrationHistory.objects.create(app_name = "fakeapp",
                                        migration = "0002_eggs",
                                        applied = datetime.datetime.now())
        
        # Did it go in?
        self.assertListEqual(
            ((u"fakeapp", u"0002_eggs"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Apply them normally
        self.assertRaises(exceptions.InconsistentMigrationHistory,
                          migrate_app,
                          migrations, target_name=None, fake=False)
        self.assertRaises(exceptions.InconsistentMigrationHistory,
                          migrate_app,
                          migrations, target_name='zero', fake=False)
        try:
            migrate_app(migrations, target_name=None, fake=False)
        except exceptions.InconsistentMigrationHistory, e:
            self.assertEqual([(migrations['0002_eggs'],
                               [migrations['0001_spam']])],
                             e.problems)
        try:
            migrate_app(migrations, target_name="zero", fake=False)
        except exceptions.InconsistentMigrationHistory, e:
            self.assertEqual([(migrations['0001_spam'],
                               [migrations['0002_eggs']])],
                             e.problems)
        
        # Nothing should have changed (no merge mode!)
        self.assertListEqual(
            ((u"fakeapp", u"0002_eggs"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Apply with merge
        migrate_app(migrations, target_name=None, merge=True, fake=False)
        
        # We should finish with all migrations
        self.assertListEqual(
            ((u"fakeapp", u"0001_spam"),
             (u"fakeapp", u"0002_eggs"),
             (u"fakeapp", u"0003_alter_spam"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Now roll them backwards
        migrate_app(migrations, target_name="0002", fake=False)
        migrate_app(migrations, target_name="0001", fake=True)
        migrate_app(migrations, target_name="zero", fake=False)
        
        # Finish with none
        self.assertEqual(list(MigrationHistory.objects.all()), [])
    
    def test_alter_column_null(self):
        def null_ok():
            from django.db import connection, transaction
            # the DBAPI introspection module fails on postgres NULLs.
            cursor = connection.cursor()
            try:
                cursor.execute("INSERT INTO southtest_spam (id, weight, expires, name) VALUES (100, 10.1, now(), NULL);")
            except:
                transaction.rollback()
                return False
            else:
                cursor.execute("DELETE FROM southtest_spam")
                transaction.commit()
                return True

        MigrationHistory.objects.all().delete()
        migrations = Migrations("fakeapp")
        
        # by default name is NOT NULL
        migrate_app(migrations, target_name="0002", fake=False)
        self.failIf(null_ok())
        self.assertListEqual(
            ((u"fakeapp", u"0001_spam"),
             (u"fakeapp", u"0002_eggs"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # after 0003, it should be NULL
        migrate_app(migrations, target_name="0003", fake=False)
        self.assert_(null_ok())
        self.assertListEqual(
            ((u"fakeapp", u"0001_spam"),
             (u"fakeapp", u"0002_eggs"),
             (u"fakeapp", u"0003_alter_spam"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )

        # make sure it is NOT NULL again
        migrate_app(migrations, target_name="0002", fake=False)
        self.failIf(null_ok(), 'name not null after migration')
        self.assertListEqual(
            ((u"fakeapp", u"0001_spam"),
             (u"fakeapp", u"0002_eggs"),),
            MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # finish with no migrations, otherwise other tests fail...
        migrate_app(migrations, target_name="zero", fake=False)
        self.assertEqual(list(MigrationHistory.objects.all()), [])
    
    def test_dependencies(self):
        
        fakeapp = Migrations("fakeapp")
        otherfakeapp = Migrations("otherfakeapp")
        
        # Test a simple path
        self.assertEqual([fakeapp['0001_spam'],
                          fakeapp['0002_eggs'],
                          fakeapp['0003_alter_spam']],
                         fakeapp['0003_alter_spam'].forwards_plan())
        
        # And a complex one.
        self.assertEqual([fakeapp['0001_spam'],
                          otherfakeapp['0001_first'],
                          otherfakeapp['0002_second'],
                          fakeapp['0002_eggs'],
                          fakeapp['0003_alter_spam'],
                          otherfakeapp['0003_third']],
                         otherfakeapp['0003_third'].forwards_plan())


class TestMigrationUtils(Monkeypatcher):
    installed_apps = ["fakeapp", "otherfakeapp"]

    def test_get_app_name(self):
        self.assertEqual(
            "southtest",
            get_app_name(self.create_fake_app("southtest.models")),
        )
        self.assertEqual(
            "baz",
            get_app_name(self.create_fake_app("foo.bar.baz.models")),
        )

class TestUtils(unittest.TestCase):

    def test_flatten(self):
        self.assertEqual([], list(flatten(iter([]))))
        self.assertEqual([], list(flatten(iter([iter([]), ]))))
        self.assertEqual([1], list(flatten(iter([1]))))
        self.assertEqual([1, 2], list(flatten(iter([1, 2]))))
        self.assertEqual([1, 2], list(flatten(iter([iter([1]), 2]))))
        self.assertEqual([1, 2], list(flatten(iter([iter([1, 2])]))))
        self.assertEqual([1, 2, 3], list(flatten(iter([iter([1, 2]), 3]))))
        self.assertEqual([1, 2, 3],
                         list(flatten(iter([iter([1]), iter([2]), 3]))))
        self.assertEqual([1, 2, 3],
                         list(flatten([[1], [2], 3])))

    def test_depends(self):
        graph = {'A1': []}
        self.assertEqual(['A1'],
                         depends('A1', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2']}
        self.assertEqual(['A1', 'A2', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'A1']}
        self.assertEqual(['A1', 'A2', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'A1', 'B1'],
                 'B1': []}
        self.assertEqual(['A1', 'A2', 'B1', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'A1', 'B2'],
                 'B1': [],
                 'B2': ['B1']}
        self.assertEqual(['A1', 'A2', 'B1', 'B2', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1', 'B1'],
                 'A3': ['A2'],
                 'B1': ['A1']}
        self.assertEqual(['A1', 'B1', 'A2', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'A1', 'B2'],
                 'B1': [],
                 'B2': ['B1', 'C1'],
                 'C1': ['B1']}
        self.assertEqual(['A1', 'A2', 'B1', 'C1', 'B2', 'A3'],
                         depends('A3', lambda n: graph[n]))
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'B2', 'A1', 'C1'],
                 'B1': ['A1'],
                 'B2': ['B1', 'C2', 'A1'],
                 'C1': ['B1'],
                 'C2': ['C1', 'A1'],
                 'C3': ['C2']}
        self.assertEqual(['A1', 'A2', 'B1', 'C1', 'C2', 'B2', 'A3'],
                         depends('A3', lambda n: graph[n]))

    def assertCircularDependency(self, trace, target, graph):
        self.assertRaises(exceptions.CircularDependency,
                          depends, target, lambda n: graph[n])
        try:
            depends(target, lambda n: graph[n])
        except exceptions.CircularDependency, e:
            self.assertEqual(trace, e.trace)

    def test_depends_cycle(self):
        graph = {'A1': ['A1']}
        self.assertCircularDependency(['A1', 'A1'],
                                      'A1', graph)
        graph = {'A1': [],
                 'A2': ['A1', 'A2'],
                 'A3': ['A2']}
        self.assertCircularDependency(['A2', 'A2'],
                                      'A3', graph)
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'A3'],
                 'A4': ['A3']}
        self.assertCircularDependency(['A3', 'A3'],
                                      'A4', graph)
        graph = {'A1': ['B1'],
                 'B1': ['A1']}
        self.assertCircularDependency(['A1', 'B1', 'A1'],
                                      'A1', graph)
        graph = {'A1': [],
                 'A2': ['A1', 'B2'],
                 'A3': ['A2'],
                 'B1': [],
                 'B2': ['B1', 'A2'],
                 'B3': ['B2']}
        self.assertCircularDependency(['B2', 'A2', 'B2'],
                                      'A3', graph)
        graph = {'A1': [],
                 'A2': ['A1', 'B3'],
                 'A3': ['A2'],
                 'B1': [],
                 'B2': ['B1', 'A2'],
                 'B3': ['B2']}
        self.assertCircularDependency(['A2', 'B3', 'B2', 'A2'],
                                      'A3', graph)
        graph = {'A1': [],
                 'A2': ['A1'],
                 'A3': ['A2', 'B2'],
                 'A4': ['A3'],
                 'B1': ['A3'],
                 'B2': ['B1']}
        self.assertCircularDependency(['A3', 'B2', 'B1', 'A3'],
                                      'A4', graph)

