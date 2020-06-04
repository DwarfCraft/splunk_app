def encode_whitespace(uri):
    """
    Encode spaces in a URI string with percent encoding
    """
    return uri.replace(" ", "%20")
