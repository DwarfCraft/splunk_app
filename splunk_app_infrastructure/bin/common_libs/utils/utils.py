import sys

if sys.version_info > (3, 0):
    from builtins import str
    unicode = str


def to_str(val):
    unicode_type = unicode if sys.version_info < (3, 0) else str
    bytes_type = str if sys.version_info < (3, 0) else bytes
    if isinstance(val, unicode_type):
        return val
    elif isinstance(val, bytes_type):
        return val.decode('utf-8')


def to_bytes(val):
    unicode_type = unicode if sys.version_info < (3, 0) else str
    bytes_type = str if sys.version_info < (3, 0) else bytes
    if isinstance(val, unicode_type):
        return val.encode('utf-8')
    elif isinstance(val, bytes_type):
        return val
