
"""
Represents an exception when the user did not have sufficient permissions.
"""
class PermissionDeniedException(Exception):
    """
    Represents an exception caused by insufficient permissions
    """
    pass

"""
Represents an exception when the user requested a lookup file that was too big.
"""
class LookupFileTooBigException(Exception):
    """
    Represents an exception caused by a lookup file being too large to load.
    """

    def __init__(self, file_size):

        # Call the base class constructor with the parameters it needs
        super(LookupFileTooBigException, self).__init__("Lookup file is too large to be loaded")

        # Remember the file-size
        self.file_size = file_size

"""
Represents an exception when the lookup file is invalid.
"""
class LookupNameInvalidException(Exception):
    """
    This exception indicates that the lookup file that was attempted to be created was invalid.
    """
    pass