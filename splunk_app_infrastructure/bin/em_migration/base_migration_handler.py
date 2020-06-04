from builtins import object


class BaseMigrationHandler(object):
    """
    This class represents a single, independent "migration" to be applied to the existing instance.
    A migration to version X_Y_Z may contain any number of migration handlers (within
    migration_handlers_X_Y_Z.py). Migration handlers belonging to a specific version are referenced
    in __init__.py in this folder which is where they get pulled in by em_migration_controller.py

    Migration in a migration handler is a two-part process:
        _calculate_changes()
            Calculation of what changes need to make (to avoid needing to rollback changes which
            can result in errors themselves)
        _apply_changes()
            Application of changes (verified as safe) from _calculate_changes()
    """

    description = None

    def __init__(self, logger, session_key):
        self.logger = logger
        self.session_key = session_key
        self.error_count = 0
        self.name = self.__class__.__name__

    def execute(self, dry_run=False):
        try:
            self.logger.info("[%s] Starting migration" % self.name)

            method_name = "_calculate_changes()"
            self.logger.info("[%s] %s" % (self.name, method_name))
            self._calculate_changes()
            if self.error_count > 0:
                raise Exception("%d errors encountered in the migration process" %
                                self.error_count)
            method_name = "_apply_changes()"
            if not dry_run:
                self.logger.info("[%s] %s" % (self.name, method_name))
                self._apply_changes()
                self.logger.info("[%s] Migration completed successfully" % self.name)
            else:
                self.logger.info("[%s] Skipping %s (dry run)" % (self.name, method_name))
        except Exception as e:
            self.logger.error("[%s] Exception encountered in %s: %s" % (self.name, method_name, e))
            raise e

    def _calculate_changes(self):
        # Calculate what changes need to be applied and save them to this object instance. Errors
        # encountered are kept track of in this function (self.error_count) for reporting down the
        # line.
        raise NotImplementedError()

    def _apply_changes(self):
        # Apply the changes saved to this object instance by _calculate_changes().
        raise NotImplementedError()
