
def raise_(ex):
    raise ex


class PackerBuildError(Exception):
    def __init__(self, message=None, _type=None):
        error_message = f"- {_type.__name__}: {message}" if _type else f"- {message}"
        super(PackerBuildError, self).__init__("PackerBuildError " + error_message)


class PackerClientError(Exception):
    pass