import sys

# Unicode type
if sys.version_info > (3,):
    text_type = str
else:
    text_type = unicode
