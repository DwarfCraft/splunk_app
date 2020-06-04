[cloudgateway_modular_input://default]
* No params required
param1 =

[alerts_ttl_modular_input://default]
ttl_days = 3

[subscription_modular_input://default]
* The minimum time an interation of the subscription processor will run for.  If an interation takes longer than the minimum, the next iteration is scheduled immediately.
minimum_iteration_time_seconds=30
* If processing jobs takes longer than this value, a warning will be logged
maximum_iteration_time_warn_threshold_seconds=300
* Define the parallelism for processing subscriptions, the special value N_CPU means the number of available cores. Otherwise it should be an integer.
subscription_processor_parallelism=N_CPU

[subscription_clean_up_modular_input://default]
* Grace period after which subscriptions and searches will be cleaned up
cleanup_threshold_seconds = 300

[registered_users_list_modular_input://default]
* No params required
param1 =

[metrics_modular_input://default]
* No params required
param1 =

[device_role_modular_input://default]
* No params required
param1 =

[ar_initialization_modular_input://default]
* No params required
param1 =

[drone_mode_subscription_modular_input://default]
* No params required
param1 =
