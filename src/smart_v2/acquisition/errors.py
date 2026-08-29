class AcquisitionError(Exception):
    """Base exception for data acquisition errors."""
    pass

class DataFetchError(AcquisitionError):
    """Raised when external data fetch fails."""
    pass

class ValidationError(AcquisitionError):
    """Raised when data validation fails."""
    pass
