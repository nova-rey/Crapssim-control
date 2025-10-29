class BundleError(Exception):
    """Base class for bundle I/O errors."""


class ExportEmptyError(BundleError):
    """Raised when required artifacts are missing for export."""


class BundleReadError(BundleError):
    """Raised when an Evo bundle cannot be read or is malformed."""


class SchemaMismatchError(BundleError):
    """Raised when bundle schemas are incompatible with CSC expectations."""
