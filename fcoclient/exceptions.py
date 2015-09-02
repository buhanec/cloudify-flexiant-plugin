# coding=UTF-8

"""Some placeholder Exceptions to match Cloudify exceptions."""


class NonRecoverableError(Exception):

    """A non-recoverable error that should cause the workflow to stop."""

    def __init__(self, message):
        """
        Initialise a new non-recoverable error.

        :param message: error message
        """
        super(Exception, self).__init__(message)


class RecoverableError(Exception):

    """A recoverable error that should cause the workflow to retry."""

    def __init__(self, message, retry_after):
        """
        Initialise a new recoverable error.

        :param message: error message
        :param retry_after: delay befor retrying
        :return:
        """
        super(Exception, self).__init__(message)

        self.retry_after = retry_after
