from typing import Optional

class OutageError(Exception):
    """Base domain exception for outage system."""
    pass

class AddressNotFoundError(OutageError):
    """Exception raised when street or house is not found in Yasno or DTEK."""
    pass

class InvalidInputError(OutageError):
    """Exception raised when request input is invalid or missing details."""
    pass

class GeocodingError(OutageError):
    """Exception raised when reverse geocoding coordinates fails."""
    pass

class OutageGroupNotFoundError(OutageError):
    """Exception raised when Yasno cannot find outage group details."""
    pass

class ClientError(OutageError):
    """Base exception for external clients (Yasno/DTEK)."""
    pass

class ClientConnectionError(ClientError):
    """Exception raised when connection or timeout occurs with external APIs."""
    pass

class ClientResponseError(ClientError):
    """Exception raised when an API returns an error response code or malformed data."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
