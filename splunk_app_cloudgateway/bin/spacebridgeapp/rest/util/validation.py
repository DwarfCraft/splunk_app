"""
Module that provides validation
utility functions
"""

def contains_empty_values(obj):

    """
    Function to return whether or
    not any values in a dict are
    empty
    :param obj: The dict being validated
    """

    return any(not v or not str(v).strip() for k,v in obj.iteritems())


def value_is_only_whitespace(val):
    """
    Function to return whether or
    not a value is only whitespace
    :param val: The string value being validated
    """
    return val and not val.strip()

def validate_deployment_name(deployment_name):
    if deployment_name:
        deployment_name = deployment_name.strip()

        # This number is from cloudgateway.conf we can set constant later
        if len(deployment_name) <= 64:
            return deployment_name

    return False

