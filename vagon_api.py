"""
Vagon Computer Management API Client

This module provides a clean, well-documented Python client for the Vagon
Computer Management API. It serves as both a functional client
and a reference implementation for API integration.

Usage:
    from vagon_api import VagonAPI

    client = VagonAPI(
        api_key="your_api_key",
        api_secret="your_api_secret"
    )

    # List all seats
    seats = client.list_seats()

    # Start a machine
    client.start_machine(machine_id=123)
"""

import hmac
import hashlib
import uuid
import time
import json
import logging
from typing import Optional, Dict, List, Any

import requests

# Configure logging for vagon_api
logger = logging.getLogger(__name__)

# Configure logging for vagon_api
logger = logging.getLogger(__name__)


class VagonAPIError(Exception):
    """Custom exception for Vagon API errors."""

    def __init__(self, status_code: int, message: str, client_code: int = None):
        self.status_code = status_code
        self.message = message
        self.client_code = client_code or status_code
        super().__init__(f"[{self.client_code}] {message}")


class VagonAPI:
    """
    Python client for Vagon Computer Management API.

    This client handles HMAC authentication and provides methods for all
    available API endpoints including seats, machines, and files management.

    Attributes:
        api_key: Your Vagon API key
        api_secret: Your Vagon API secret
        base_url: API base URL (default: production)

    Example:
        >>> client = VagonAPI("api_key", "api_secret")
        >>> seats = client.list_seats()
        >>> print(f"Found {seats['count']} seats")
    """

    # API Base URLs
    PRODUCTION_URL = "https://api.vagon.io"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = PRODUCTION_URL
    ):
        """
        Initialize the Vagon API client.

        Args:
            api_key: Your API key from organization settings
            api_secret: Your API secret from organization settings
            base_url: API base URL (default: production)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip('/')

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    def _generate_hmac_signature(
        self,
        method: str,
        path: str,
        timestamp: str,
        nonce: str,
        body: str = ''
    ) -> str:
        """
        Generate HMAC-SHA256 signature for API authentication.

        The signature is calculated from:
        api_key + HTTP_METHOD + request_path + timestamp + nonce + request_body

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: Request path (e.g., '/organization-management/v1/seats')
            timestamp: Unix timestamp in milliseconds
            nonce: Unique request identifier (UUID recommended)
            body: Request body as string (empty for GET requests)

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        signature_string = f"{self.api_key}{method}{path}{timestamp}{nonce}{body}"

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _generate_auth_header(self, method: str, path: str, body: str = '') -> str:
        """
        Generate the complete Authorization header for API requests.

        Format: HMAC api_key:signature:nonce:timestamp

        Args:
            method: HTTP method
            path: Request path
            body: Request body as string

        Returns:
            Complete Authorization header value
        """
        nonce = str(uuid.uuid4())
        timestamp = str(int(time.time() * 1000))

        signature = self._generate_hmac_signature(
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body
        )

        return f"HMAC {self.api_key}:{signature}:{nonce}:{timestamp}"

    # =========================================================================
    # HTTP REQUEST HANDLING
    # =========================================================================

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        body: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an authenticated HTTP request to the Vagon API.

        Args:
            method: HTTP method (GET, POST, DELETE)
            path: API endpoint path
            params: Query parameters (optional)
            body: Request body as dict (optional)

        Returns:
            Parsed JSON response

        Raises:
            VagonAPIError: If the API returns an error response
        """
        # Serialize body to JSON string for HMAC calculation
        body_str = json.dumps(body) if body else ''

        # Generate authentication header
        auth_header = self._generate_auth_header(method, path, body_str)

        # Prepare headers
        headers = {"Authorization": auth_header}
        if body:
            headers["Content-Type"] = "application/json"

        # Debug: Log request details
        full_url = f"{self.base_url}{path}"
        logger.info(f"\n{'='*60}")
        logger.info(f"[VAGON API REQUEST]")
        logger.info(f"  Method: {method}")
        logger.info(f"  URL: {full_url}")
        if params:
            logger.info(f"  Params: {params}")
        if body:
            logger.info(f"  Body: {json.dumps(body, indent=2)}")
        logger.info(f"{'='*60}")

        # Make the request
        response = requests.request(
            method=method,
            url=full_url,
            headers=headers,
            params=params,
            data=body_str if body_str else None
        )

        # Debug: Log response details
        logger.info(f"\n[VAGON API RESPONSE]")
        logger.info(f"  Status: {response.status_code}")
        logger.info(f"  Headers: {dict(response.headers)}")
        try:
            response_json = response.json() if response.content else {}
            logger.info(f"  Body: {json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            logger.warning(f"  Body (raw, not JSON): {response.text[:500]}")
            response_json = {}
        logger.info(f"{'='*60}\n")

        # Handle errors
        if not response.ok:
            error_message, client_code = self._parse_error_response(response)
            logger.error(f"[VAGON API ERROR] client_code={client_code}, status={response.status_code}, message={error_message}")
            logger.error(f"  Response text: {response.text[:500]}")
            logger.error(f"  Response headers: {dict(response.headers)}")
            raise VagonAPIError(response.status_code, error_message, client_code)

        # Return parsed response
        return response_json

    def _parse_error_response(self, response: requests.Response) -> tuple:
        """
        Extract error message and client_code from API response.

        Returns:
            Tuple of (error_message, client_code)
        """
        try:
            error_data = response.json()
            message = error_data.get('message', error_data.get('error', 'Unknown error'))
            client_code = error_data.get('client_code', response.status_code)
            logger.info(f"[PARSE ERROR] Parsed JSON error: message={message}, client_code={client_code}")
            return message, client_code
        except json.JSONDecodeError as e:
            logger.warning(f"[PARSE ERROR] Could not parse JSON. Status: {response.status_code}, Text: {response.text[:200]}, Error: {str(e)}")
            # Try to extract meaningful error message from text
            error_text = response.text.strip() if response.text else ""
            if not error_text:
                error_text = f"HTTP {response.status_code} - No response body"
            return error_text, response.status_code
        except KeyError as e:
            logger.warning(f"[PARSE ERROR] Missing key in error response: {str(e)}, Response: {response.text[:200]}")
            return response.text or f"HTTP {response.status_code}", response.status_code

    # =========================================================================
    # SEATS ENDPOINTS
    # =========================================================================

    def list_seats(
        self,
        page: int = 1,
        per_page: int = 20,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all seats in the organization.

        Seats represent user allocations within the organization. Each seat
        can have an associated machine and user.

        Args:
            page: Page number for pagination (default: 1)
            per_page: Number of items per page (default: 20)
            query: Search query to filter seats by user (optional)

        Returns:
            Dict containing:
                - seats: List of seat objects
                - count: Total number of seats
                - page: Current page number
                - next_page: Next page number or None

        Example:
            >>> seats = client.list_seats(page=1, per_page=10)
            >>> for seat in seats['seats']:
            ...     print(f"{seat['name']}: {seat['status']}")
        """
        params = {"page": page, "per_page": per_page}
        if query:
            params["q"] = query

        return self._request("GET", "/organization-management/v1/seats", params=params)

    def get_seat(self, seat_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific seat.

        Args:
            seat_id: The unique identifier of the seat

        Returns:
            Seat object containing:
                - id: Seat ID
                - status: Seat status (active, inactive)
                - name: Seat name
                - user: Associated user information
                - machine: Associated machine information
                - file_storage_size: Total file storage in bytes
                - remaining_usage: Remaining usage credits

        Example:
            >>> seat = client.get_seat(123)
            >>> print(f"Seat: {seat['name']}")
            >>> print(f"User: {seat['user']['email']}")
        """
        return self._request("GET", f"/organization-management/v1/seats/{seat_id}")

    def list_seat_content(self, seat_id: int, path: str) -> Dict[str, Any]:
        """
        List content of a specific path on the seat's machine.

        Note: The machine must be running to use this endpoint.

        Args:
            seat_id: The seat ID
            path: Path on the machine to list (e.g., '/home/user')

        Returns:
            Dict containing:
                - content: Object with 'files' and 'directories' arrays

        Example:
            >>> content = client.list_seat_content(123, '/home/user')
            >>> for file in content['content']['files']:
            ...     print(f"{file['name']} ({file['size']} bytes)")
        """
        return self._request(
            "POST",
            f"/organization-management/v1/seats/{seat_id}/list-content",
            body={"path": path}
        )

    def get_seat_files(
        self,
        seat_id: int,
        parent_id: int = 0,
        page: int = 1,
        per_page: int = 20,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get files and directories for a specific seat's file storage.

        Args:
            seat_id: The seat ID
            parent_id: Parent directory ID (0 for root)
            page: Page number for pagination
            per_page: Number of items per page
            query: Search query to filter files

        Returns:
            Dict containing:
                - files: List of file/directory objects
                - current: Current directory information
                - count: Total number of items
                - page: Current page
                - next_page: Next page or None

        Example:
            >>> files = client.get_seat_files(123, parent_id=0)
            >>> for f in files['files']:
            ...     print(f"{f['name']} - {f['object_type']}")
        """
        params = {"parent_id": parent_id, "page": page, "per_page": per_page}
        if query:
            params["q"] = query

        return self._request(
            "GET",
            f"/organization-management/v1/seats/{seat_id}/files",
            params=params
        )

    # =========================================================================
    # MACHINES ENDPOINTS
    # =========================================================================

    def get_machine(self, machine_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific machine.

        Args:
            machine_id: The unique identifier of the machine

        Returns:
            Machine object containing:
                - id: Machine ID
                - status: Current status (running, stopped, etc.)
                - name: Machine name
                - region: Deployment region
                - machine_type: Machine type/tier
                - last_session_start_at: Last session start timestamp

        Example:
            >>> machine = client.get_machine(456)
            >>> print(f"Machine {machine['name']} is {machine['status']}")
        """
        return self._request("GET", f"/organization-management/v1/machines/{machine_id}")

    def start_machine(
        self,
        machine_id: int,
        machine_type_id: Optional[int] = None,
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a stopped machine.

        Optionally change the machine type or region when starting.

        Args:
            machine_id: The machine ID to start
            machine_type_id: New machine type ID (optional)
            region: New region (optional, e.g., 'dublin')

        Returns:
            Empty dict on success

        Raises:
            VagonAPIError: With status codes:
                - 440: AWS Capacity Error
                - 469: Disk resizing in progress
                - 480: Insufficient Funds
                - 4110: Subscription Payment Waiting
                - 4201: Machine is not ready

        Example:
            >>> client.start_machine(456)
            >>> # Or with new machine type
            >>> client.start_machine(456, machine_type_id=5)
        """
        body = {}
        if machine_type_id is not None:
            body["machine_type_id"] = machine_type_id
        if region is not None:
            body["region"] = region

        return self._request(
            "POST",
            f"/organization-management/v1/machines/{machine_id}/start",
            body=body if body else None
        )

    def stop_machine(self, machine_id: int) -> Dict[str, Any]:
        """
        Stop a running machine.

        Args:
            machine_id: The machine ID to stop

        Returns:
            Empty dict on success

        Example:
            >>> client.stop_machine(456)
        """
        return self._request(
            "POST",
            f"/organization-management/v1/machines/{machine_id}/stop",
            body={"gracefully": True} # It await for any file upload to complete before stopping the machine
        )

    def reset_machine(self, machine_id: int) -> Dict[str, Any]:
        """
        Reset a stopped machine.

        This will:
        - Delete all machine images
        - Mark active session as reset
        - Terminate the EC2 instance if it exists
        - Clear the seat's silver image association

        Note: The machine must be stopped (not running) to reset it.

        Args:
            machine_id: The machine ID to reset

        Returns:
            Empty dict on success

        Raises:
            VagonAPIError: With status codes:
                - 400: Machine is running (must be stopped first)
                - 403: Forbidden (member trying to reset another member's machine)
                - 404: Machine not found

        Example:
            >>> client.reset_machine(456)
        """
        return self._request(
            "POST",
            f"/organization-management/v1/machines/{machine_id}/reset"
        )

    def create_machine_access(
        self,
        machine_id: int,
        expires_in: int
    ) -> Dict[str, Any]:
        """
        Create a temporary access link for a machine.

        This generates a unique URL that can be used to access the machine
        without requiring user authentication.

        Args:
            machine_id: The machine ID
            expires_in: Link expiration time in seconds

        Returns:
            Dict containing:
                - uid: Unique access identifier
                - expires_at: Expiration timestamp
                - connection_link: URL to access the machine

        Example:
            >>> access = client.create_machine_access(456, expires_in=3600)
            >>> print(f"Access link: {access['connection_link']}")
            >>> print(f"Expires at: {access['expires_at']}")
        """
        return self._request(
            "POST",
            f"/organization-management/v1/machines/{machine_id}/access",
            body={"expires_in": expires_in}
        )

    def get_seat_available_machine_types(self, seat_id: int) -> List[Dict[str, Any]]:
        """
        Get available machine types for a specific seat.

        The machine types are determined by the seat's organization seat plan.

        Args:
            seat_id: The seat ID

        Returns:
            List of machine type objects in JSON:API format (flattened)

        Example:
            >>> machine_types = client.get_seat_available_machine_types(123)
            >>> for mt in machine_types:
            ...     print(f"{mt['name']} - {mt['friendly_name']}")
        """
        result = self._request(
            "GET",
            f"/organization-management/v1/seats/{seat_id}/available-machine-types"
        )
        # API returns machine types wrapped in a "machine_types" key
        machine_types = result.get("machine_types", [])
        if isinstance(machine_types, list):
            return [flatten_jsonapi_resource(item) for item in machine_types]
        return []

    def set_machine_type(
        self,
        machine_id: int,
        machine_type_id: int
    ) -> Dict[str, Any]:
        """
        Set the machine type for a specific machine.

        The machine type must be available in the machine's seat plan.

        Args:
            machine_id: The machine ID
            machine_type_id: Machine type ID to set

        Returns:
            Empty dict on success

        Raises:
            VagonAPIError: With status codes:
                - 400: Machine type is not available in the seat's plan
                - 404: Machine not found or belongs to different organization

        Example:
            >>> client.set_machine_type(456, machine_type_id=5)
        """
        return self._request(
            "POST",
            f"/organization-management/v1/machines/{machine_id}/machine-type",
            body={"machine_type_id": machine_type_id}
        )

    # =========================================================================
    # FILES ENDPOINTS
    # =========================================================================

    def list_files(
        self,
        parent_id: int = 0,
        page: int = 1,
        per_page: int = 20,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List shared files and directories for the organization.

        Args:
            parent_id: Parent directory ID (0 for root)
            page: Page number for pagination
            per_page: Number of items per page
            query: Search query to filter files

        Returns:
            Dict containing:
                - files: List of file/directory objects
                - current: Current directory information
                - count: Total number of items
                - page: Current page
                - next_page: Next page or None

        Example:
            >>> files = client.list_files()
            >>> for f in files['files']:
            ...     print(f"{f['name']} ({f['object_type']})")
        """
        params = {"parent_id": parent_id, "page": page, "per_page": per_page}
        if query:
            params["q"] = query

        return self._request("GET", "/organization-management/v1/files", params=params)

    def create_directory(
        self,
        name: str,
        parent_id: int = 0,
        seat_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new directory.

        Args:
            name: Directory name
            parent_id: Parent directory ID (0 for root)
            seat_id: Seat ID for seat-specific storage (optional)

        Returns:
            Dict containing:
                - id: New directory ID
                - uid: Unique identifier

        Example:
            >>> result = client.create_directory("Projects", parent_id=0)
            >>> print(f"Created directory with ID: {result['id']}")
        """
        body = {
            "file_name": name,
            "object_type": "directory",
            "parent_id": parent_id
        }
        if seat_id is not None:
            body["seat_id"] = seat_id

        return self._request("POST", "/organization-management/v1/files", body=body)

    def create_file(
        self,
        name: str,
        parent_id: int,
        content_type: str,
        size: int,
        chunk_size: int = 250,
        overwrite: bool = False,
        seat_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new file and get multipart upload URLs.

        This initiates a multipart upload process. Use the returned upload_urls
        to upload file chunks, then call complete_upload() to finalize.

        Args:
            name: File name
            parent_id: Parent directory ID
            content_type: MIME type (e.g., 'application/pdf')
            size: File size in bytes
            chunk_size: Chunk size in MB (default: 250)
            overwrite: Overwrite existing file (default: False)
            seat_id: Seat ID for seat-specific storage (optional)

        Returns:
            Dict containing:
                - id: File ID
                - uid: Unique identifier
                - upload_urls: List of presigned URLs for uploading chunks
                - chunk_size: Chunk size used

        Example:
            >>> result = client.create_file(
            ...     name="document.pdf",
            ...     parent_id=0,
            ...     content_type="application/pdf",
            ...     size=1024000
            ... )
            >>> for i, url in enumerate(result['upload_urls']):
            ...     # Upload chunk i to url
            ...     pass
        """
        body = {
            "file_name": name,
            "object_type": "file",
            "parent_id": parent_id,
            "content_type": content_type,
            "size": size,
            "chunk_size": chunk_size,
            "overwrite": overwrite
        }
        if seat_id is not None:
            body["seat_id"] = seat_id

        return self._request("POST", "/organization-management/v1/files", body=body)

    def complete_upload(
        self,
        file_id: int,
        parts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Complete a multipart file upload.

        After uploading all file chunks to the presigned URLs, call this
        method with the part numbers and ETags to finalize the upload.

        Args:
            file_id: The file ID from create_file()
            parts: List of dicts with 'part_number' and 'etag' keys

        Returns:
            Dict containing:
                - uid: File unique identifier
                - download_url: URL to download the file

        Example:
            >>> parts = [
            ...     {"part_number": 1, "etag": '"etag1"'},
            ...     {"part_number": 2, "etag": '"etag2"'}
            ... ]
            >>> result = client.complete_upload(789, parts)
            >>> print(f"Download URL: {result['download_url']}")
        """
        return self._request(
            "POST",
            f"/organization-management/v1/files/{file_id}/complete",
            body={"parts": parts}
        )

    def get_download_url(self, file_id: int) -> Dict[str, Any]:
        """
        Get a temporary download URL for a file.

        Args:
            file_id: The file ID

        Returns:
            Dict containing:
                - url: Presigned download URL
                - size: File size in bytes
                - name: File name
                - content_type: MIME type

        Example:
            >>> download = client.get_download_url(789)
            >>> print(f"Download {download['name']} from {download['url']}")
        """
        return self._request("GET", f"/organization-management/v1/files/{file_id}/download")

    def delete_file(self, file_id: int) -> Dict[str, Any]:
        """
        Delete a file or directory.

        Note: Cannot delete root folders.

        Args:
            file_id: The file or directory ID to delete

        Returns:
            Empty dict on success

        Raises:
            VagonAPIError: With status code 450 if trying to delete root

        Example:
            >>> client.delete_file(789)
        """
        return self._request("DELETE", f"/organization-management/v1/files/{file_id}")

    def get_capacity(self, seat_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get storage capacity information.

        Args:
            seat_id: Seat ID for seat-specific capacity (optional)

        Returns:
            Dict containing:
                - total: Total storage in bytes
                - in_use: Used storage in bytes
                - team: Team storage info (total, in_use)

        Example:
            >>> capacity = client.get_capacity()
            >>> used_gb = capacity['in_use'] / (1024**3)
            >>> total_gb = capacity['total'] / (1024**3)
            >>> print(f"Using {used_gb:.2f} GB of {total_gb:.2f} GB")
        """
        params = {}
        if seat_id is not None:
            params["seat_id"] = seat_id

        return self._request(
            "GET",
            "/organization-management/v1/files/capacity",
            params=params if params else None
        )

    # =========================================================================
    # USER ACTION LOGS
    # =========================================================================

    def list_user_action_logs(
        self,
        start_date: str,
        end_date: str,
        action_type: Optional[str] = None,
        user_email: Optional[str] = None,
        organization_machine_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch recent user action logs (last 30 days) with optional filters.

        Args:
            start_date: ISO-8601 start datetime (inclusive)
            end_date: ISO-8601 end datetime (inclusive)
            action_type: Optional action type filter
            user_email: Optional user email filter
            organization_machine_id: Optional machine ID filter

        Returns:
            Dict containing:
                - logs: List of log entries
                - count: Total number of returned logs
                - start_date: Requested start date
                - end_date: Requested end date
        """
        params: Dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date
        }
        if action_type:
            params["action_type"] = action_type
        if user_email:
            params["user_email"] = user_email
        if organization_machine_id is not None:
            params["organization_machine_id"] = organization_machine_id

        return self._request(
            "GET",
            "/organization-management/v1/user-action-logs",
            params=params
        )

    def list_softwares(self) -> Dict[str, Any]:
        """
        List all available softwares and golden images.

        Returns:
            Dict containing:
                - software: List of software objects (id, name, size)
                - golden_images: List of golden image objects (id, name, size)

        Example:
            >>> result = client.list_softwares()
            >>> for software in result['software']:
            ...     print(f"{software['name']}: {software['size']} GB")
        """
        return self._request("GET", "/organization-management/v1/software")

    def create_seat(
        self,
        seat_plan_id: int,
        quantity: int = 1,
        software_ids: Optional[List[int]] = None,
        base_image_id: Optional[int] = None,
        permissions: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """
        Create new seats with balance payment.

        Args:
            seat_plan_id: The seat plan ID (required)
            quantity: Number of seats to create (default: 1)
            software_ids: List of software IDs to pre-install (optional)
            base_image_id: Base golden image ID (optional, uses default if not provided)
            permissions: Dict of permission field names to boolean values (optional)

        Returns:
            Dict containing:
                - seats: List of created seat objects
                - count: Number of seats created
                - silver_image: Silver image object if software_ids or base_image_id provided

        Example:
            >>> result = client.create_seat(
            ...     seat_plan_id=1,
            ...     quantity=2,
            ...     software_ids=[1, 2, 3],
            ...     permissions={
            ...         "screen_recording_enabled": True,
            ...         "input_recording_enabled": True
            ...     }
            ... )
            >>> print(f"Created {result['count']} seats")
        """
        data = {
            "seat_plan_id": seat_plan_id,
            "quantity": quantity
        }
        if software_ids:
            data["software_ids"] = software_ids
        if base_image_id:
            data["base_image_id"] = base_image_id
        if permissions:
            data["permissions"] = permissions

        return self._request("POST", "/organization-management/v1/seats", body=data)

    def get_permission_fields(self) -> Dict[str, Any]:
        """
        Get all available permission fields with their types and default values.

        Returns:
            Dict containing:
                - permission_fields: List of permission field objects with name, type, and default

        Example:
            >>> result = client.get_permission_fields()
            >>> for field in result['permission_fields']:
            ...     print(f"{field['name']}: {field['default']}")
        """
        return self._request("GET", "/organization-management/v1/seats/permission-fields")

    def get_archived_user_action_logs_urls(
        self,
        start_date: str,
        end_date: str,
        expires_in: int = 600
    ) -> Dict[str, Any]:
        """
        Get presigned S3 URLs for archived user action logs (older than 30 days).

        Args:
            start_date: ISO-8601 start date (YYYY-MM-DD)
            end_date: ISO-8601 end date (YYYY-MM-DD)
            expires_in: URL expiration time in seconds (default 600)

        Returns:
            Dict containing:
                - download_urls: List of download URL info
                - count: Number of URLs
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "expires_in": expires_in
        }

        return self._request(
            "GET",
            "/organization-management/v1/user-action-logs/archived-download-urls",
            params=params
        )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_bytes(size: int) -> str:
    """
    Format bytes to human-readable string.

    Args:
        size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def flatten_jsonapi_resource(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a JSON:API resource into a simple dict.

    JSON:API format:
        {
            "id": "123",
            "type": "seat",
            "attributes": {
                "name": "Seat 1",
                "status": "active",
                ...
            }
        }

    Flattened format:
        {
            "id": "123",
            "type": "seat",
            "name": "Seat 1",
            "status": "active",
            ...
        }

    Args:
        resource: JSON:API resource object

    Returns:
        Flattened dict with id, type, and all attributes at top level
    """
    if not resource:
        return {}

    result = {
        'id': resource.get('id'),
        'type': resource.get('type')
    }

    # Flatten attributes
    attributes = resource.get('attributes', {})
    if attributes:
        result.update(attributes)

        # Recursively flatten nested resources (user, machine)
        for key in ['user', 'machine']:
            if key in result and isinstance(result[key], dict) and 'attributes' in result[key]:
                result[key] = flatten_jsonapi_resource(result[key])

    return result


def flatten_jsonapi_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten a list of JSON:API resources.

    Args:
        items: List of JSON:API resource objects

    Returns:
        List of flattened dicts
    """
    return [flatten_jsonapi_resource(item) for item in items]
