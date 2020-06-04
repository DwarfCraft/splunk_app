from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError

@defer.inlineCallbacks
def check_and_raise_error(response, request_context, request_type, valid_codes=None):
    """
    Function checks for and raises an error if necessary
    from a deferred response
    @param response: deferred object response
    @param request_context:
    @param request_type: Type of request that was made (used in error logging)
    """
    if valid_codes is None:
        valid_codes = [http.OK]

    if response.code not in valid_codes:
        error = yield response.text()
        error_message = "Request: {} failed. status_code={}, error={}, {}"\
            .format(request_type, response.code, error, request_context)
        raise SpacebridgeApiRequestError(error_message, status_code=response.code)


