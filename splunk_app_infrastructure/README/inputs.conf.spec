[em_entity_class_manager://<name>]
# A modular input which is responsible for managing entity class
log_level = <DEBUG|INFO|WARNING|ERROR>
# The logging level of the modular input.  Defaults to WARNING

[aws_input_restarter://<name>]
# A modular input which is responsible for restarting AWS CloudWatch inputs to workaround EC2 discovery issues
log_level = <DEBUG|INFO|WARNING|ERROR>
# The logging level of the modular input.  Defaults to WARNING

[em_entity_migration://<name>]
# A modular input which is responsible for migrating entity to message bus URL
log_level = <DEBUG|INFO|WARNING|ERROR>
# The logging level of the modular input.  Defaults to WARNING
publish_url= <string>
# The publish URL of the message bus, i.e: servicesNS/nobody/SA-ITOA/itoa_entity_exchange/publish

[em_group_metadata_manager://<name>]
# A modular input which is responsible for managing group class
log_level = <DEBUG|INFO|WARNING|ERROR>
# The logging level of the modular input.  Defaults to WARNING

[em_migration_controller://<name>]
# A modular input which is responsible for migrating an instance from a previous
# version of SAI to the current version
# The logging level of the modular input.  Defaults to INFO
log_level = <DEBUG|INFO|WARN|ERROR>
# If true, changes will not be applied after calculation
dry_run = <int>
