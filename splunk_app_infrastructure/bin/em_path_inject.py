# Copyright 2016 Splunk Inc. All rights reserved.
"""
em_path_inject module is used to inject both internal and external python libs into
sys path, so that they can be imported at program runtime while won't be accidentally
imported by python scripts of other Splunk apps. (Due to the sad reality that splunk automatically
add all python modules inside of app's bin folder to sys path).

If you want to import third-party libraries that are not directly contained in the `bin` folder of
the app in a python module. Run
```
import em_path_inject  # noqa
```
at the very top of the file.
"""

# Standard Python Libraries
import os
import sys
import re
# Third-Party Libraries
# N/A
# Custom Libraries

# DO NOT CHANGE THE ORDER OF THIS LIST
# See https://splunk.slack.com/archives/GA1C33PQA/p1569967891050300
libs = ['common_libs', 'external_lib']

pattern = re.compile(r"[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$")
# Keep only SAI's bin folder and libs shipped with core in sys path
new_paths = [path for path in sys.path if not pattern.search(
    path) or 'splunk_app_infrastructure' in path]

for lib_name in libs:
    lib_path = os.path.sep.join([os.path.dirname(__file__), lib_name])
    # Remove if already exists and insert at the beginning
    try:
        new_paths.remove(lib_path)
    except ValueError:
        pass
    new_paths.insert(0, lib_path)

if sys.version_info[0] < 3:
    new_paths.append(os.path.sep.join([os.path.dirname(__file__), 'external_lib_py2']))

sys.path = new_paths
