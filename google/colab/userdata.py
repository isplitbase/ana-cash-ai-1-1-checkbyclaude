import os
def get(key: str, default=None):
    return os.environ.get(key, default)
