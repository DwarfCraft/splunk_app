import os
import sys

def add_python_version_specific_paths():
    sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib'))

    if sys.version_info < (3, 0):
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'py2'))
    else:
        # The python protobuf compiler doesn't play nice with imports in python 3
        # See: https://github.com/protocolbuffers/protobuf/issues/1491
        # One way to fix that is to explicitly add the modules to the python path
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'py3'))
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib/spacebridge_protocol'))
        sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib/splapp_protocol'))


add_python_version_specific_paths()
