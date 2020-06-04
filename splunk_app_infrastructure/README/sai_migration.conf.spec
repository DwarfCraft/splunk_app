# This .conf file just serves to persist miscellaneous information used for version migrations

[metadata]
latest_migrated_version = <string>
# This is the last known migrated version of the SAI app on the instance
# "?.0.0" is a dummy value to indicate we don't know what version this is. It could either be an
# upgrade or a new installation.

migration_running = <0|1>
# This boolean value indicates if the migration process is currently running or not
