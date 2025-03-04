from copy import copy
from cStringIO import StringIO
import datetime
import inspect
import sys
import traceback

from django.core.management import call_command
from django.db import models

from south import exceptions
from south.db import db
from south.models import MigrationHistory
from south.signals import ran_migration


class Migrator(object):
    def __init__(self, verbosity=0):
        self.verbosity = int(verbosity)

    @staticmethod
    def title(target):
        raise NotImplementedError()

    def print_title(self, target):
        if self.verbosity:
            print self.title(target)
        
    @staticmethod
    def status(target):
        raise NotImplementedError()

    def print_status(self, migration):
        status = self.status(migration)
        if self.verbosity and status:
            print status

    @staticmethod
    def orm(migration):
        raise NotImplementedError()

    def backwards(self, migration):
        return self._wrap_direction(migration.backwards(), self.orm(migration))

    def direction(self, migration):
        raise NotImplementedError()

    @staticmethod
    def _wrap_direction(direction, orm):
        args = inspect.getargspec(direction)
        if len(args[0]) == 1:
            # Old migration, no ORM should be passed in
            return direction
        return (lambda: direction(orm))

    @staticmethod
    def record(migration):
        raise NotImplementedError()

    def run_migration_error(self, migration, extra_info=''):
        return (' ! Error found during real run of migration! Aborting.\n'
                '\n'
                ' ! Since you have a database that does not support running\n'
                ' ! schema-altering statements in transactions, we have had \n'
                ' ! to leave it in an interim state between migrations.\n'
                '%s\n'
                ' ! The South developers regret this has happened, and would\n'
                ' ! like to gently persuade you to consider a slightly\n'
                ' ! easier-to-deal-with DBMS.\n') % extra_info

    def run_migration(self, migration):
        migration_function = self.direction(migration)
        db.start_transaction()
        try:
            migration_function()
            db.execute_deferred_sql()
        except:
            db.rollback_transaction()
            if not db.has_ddl_transactions:
                print self.run_migration_error(migration)
            raise
        else:
            db.commit_transaction()

    def run(self, migration):
        # Get the correct ORM.
        db.current_orm = self.orm(migration)
        # If the database doesn't support running DDL inside a transaction
        # *cough*MySQL*cough* then do a dry run first.
        if not db.has_ddl_transactions:
            dry_run = DryRunMigrator(migrator=self, ignore_fail=False)
            dry_run.run_migration(migration)
        return self.run_migration(migration)

    def done_migrate(self, migration):
        db.start_transaction()
        try:
            # Record us as having done this
            self.record(migration)
        except:
            db.rollback_transaction()
            raise
        else:
            db.commit_transaction()

    def send_ran_migration(self, migration):
        ran_migration.send(None,
                           app=migration.app_name(),
                           migration=migration,
                           method=self.__class__.__name__.lower())

    def migrate(self, migration):
        """
        Runs the specified migration forwards/backwards, in order.
        """
        app = migration.migrations._migrations
        migration_name = migration.name()
        self.print_status(migration)
        result = self.run(migration)
        self.done_migrate(migration)
        self.send_ran_migration(migration)
        return result

    def migrate_many(self, target, migrations):
        raise NotImplementedError()


class MigratorWrapper(object):
    def __init__(self, migrator, *args, **kwargs):
        self._migrator = copy(migrator)
        attributes = dict([(k, getattr(self, k))
                           for k in self.__class__.__dict__.iterkeys()
                           if not k.startswith('__')])
        self._migrator.__dict__.update(attributes)

    def __getattr__(self, name):
        return getattr(self._migrator, name)


class DryRunMigrator(MigratorWrapper):
    def __init__(self, ignore_fail=True, *args, **kwargs):
        super(DryRunMigrator, self).__init__(*args, **kwargs)
        self._ignore_fail = ignore_fail

    def _run_migration(self, migration):
        if migration.no_dry_run() and self.verbosity:
            print " - Migration '%s' is marked for no-dry-run."
            return
        db.dry_run = True
        db.debug, old_debug = False, db.debug
        pending_creates = db.get_pending_creates()
        db.start_transaction()
        migration_function = self.direction(migration)
        try:
            migration_function()
        except:
            raise exceptions.FailedDryRun(sys.exc_info())
        finally:
            db.rollback_transactions_dry_run()
            db.debug = old_debug
            db.clear_run_data(pending_creates)
            db.dry_run = False

    def run_migration(self, migration):
        try:
            self._run_migration(migration)
        except exceptions.FailedDryRun:
            if self._ignore_fail:
                return False
            raise

    def done_migrate(self, *args, **kwargs):
        pass

    def send_ran_migration(self, *args, **kwargs):
        pass


class FakeMigrator(MigratorWrapper):
    def run(self, migration):
        if self.verbosity:
            print '   (faked)'

    def send_ran_migration(self, *args, **kwargs):
        pass


class LoadInitialDataMigrator(MigratorWrapper):
    def load_initial_data(self, target):
        if target != target.migrations[-1]:
            return
        # Load initial data, if we ended up at target
        if self.verbosity:
            print " - Loading initial data for %s." % target.app_name()
        # Override Django's get_apps call temporarily to only load from the
        # current app
        old_get_apps = models.get_apps
        models.get_apps = lambda: [models.get_app(target.app_name())]
        try:
            call_command('loaddata', 'initial_data', verbosity=self.verbosity)
        finally:
            models.get_apps = old_get_apps

    def migrate_many(self, target, migrations):
        migrator = self._migrator
        result = migrator.__class__.migrate_many(migrator, target, migrations)
        if result:
            self.load_initial_data(target)
        return True


class Forwards(Migrator):
    """
    Runs the specified migration forwards, in order.
    """
    torun = 'forwards'

    @staticmethod
    def title(target):
        return " - Migrating forwards to %s." % target.name()

    @staticmethod
    def status(migration):
        return ' > %s' % migration

    @staticmethod
    def orm(migration):
        return migration.orm()

    def forwards(self, migration):
        return self._wrap_direction(migration.forwards(), self.orm(migration))

    direction = forwards

    @staticmethod
    def record(migration):
        # Record us as having done this
        record = MigrationHistory.for_migration(migration)
        record.applied = datetime.datetime.utcnow()
        record.save()

    def format_backwards(self, migration):
        old_debug, old_dry_run = db.debug, db.dry_run
        db.debug = db.dry_run = True
        stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            self.backwards(migration)()
            return sys.stdout.getvalue()
        except:
            raise
        finally:
            db.debug, db.dry_run = old_debug, old_dry_run
            sys.stdout = stdout

    def run_migration_error(self, migration, extra_info=''):
        extra_info = ('\n'
                      '! You *might* be able to recover with:'
                      '%s'
                      '%s' %
                      (self.format_backwards(migration), extra_info))
        return super(Forwards, self).run_migration_error(migration, extra_info)

    def migrate_many(self, target, migrations):
        try:
            for migration in migrations:
                result = self.migrate(migration)
                if result is False: # The migrations errored, but nicely.
                    return False
        finally:
            # Call any pending post_syncdb signals
            db.send_pending_create_signals()
        return True


class Backwards(Migrator):
    """
    Runs the specified migration backwards, in order.
    """
    torun = 'backwards'

    @staticmethod
    def title(target):
        return " - Migrating backwards to just after %s." % target.name()

    @staticmethod
    def status(migration):
        return ' < %s' % migration

    @staticmethod
    def orm(migration):
        return migration.prev_orm()

    direction = Migrator.backwards

    @staticmethod
    def record(migration):
        # Record us as having not done this
        record = MigrationHistory.for_migration(migration)
        if record.id is not None:
            record.delete()

    def migrate_many(self, target, migrations):
        for migration in migrations:
            self.migrate(migration)
        return True



