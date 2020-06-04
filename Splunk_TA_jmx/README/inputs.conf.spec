[jmx://<name>]
config_file = <String> name of the config file. Defaults to config.xml
config_file_dir = <String> optional alternate location for config files
polling_frequency = <Integer> how frequently to execute the polling in seconds. Defaults to 60
python.version = {default|python|python2|python3}
* For Splunk 8.0.x and Python scripts only, selects which Python version to use.
* Either "default" or "python" select the system-wide default Python version.
* Optional.
* Default: not set; uses the system-wide Python version.
