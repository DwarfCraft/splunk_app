import socket


def default_shard_id():
    return socket.gethostname()
