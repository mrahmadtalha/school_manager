"""The one error type every license operation raises."""


class LicenseError(Exception):
    """A license key could not be accepted.  ``code`` is machine-readable."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
