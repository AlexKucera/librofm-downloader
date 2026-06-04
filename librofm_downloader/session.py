"""HTTP session for Libro.fm API — auth, library fetch, and rate-limited downloads."""

from __future__ import annotations

import threading

import httpx

# Maximum concurrent Libro.fm API calls (not CDN downloads).
# Configurable constant — not user-facing.
API_SEMAPHORE_CAPACITY = 3


class AuthError(Exception):
    """Authentication failed (bad credentials, network error, etc.)."""


class M4BUnavailableError(Exception):
    """M4B format is not available for this book (404 from API)."""


class LibroFmSession:
    """Libro.fm API session with OAuth2 password grant and library fetching.

    Constructs a single shared ``httpx.Client`` at instantiation time.
    All endpoint methods reuse this client, so transport injection (for
    testing) happens once via the ``transport`` keyword argument.
    """

    DEFAULT_HEADERS = {
        "X-LibroFm-AppVer": "7.34.8",
        "User-Agent": "okhttp/5.3.2",
    }

    def __init__(
        self,
        base_url: str = "https://libro.fm",
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._access_token: str | None = None
        self._api_semaphore = threading.Semaphore(API_SEMAPHORE_CAPACITY)

        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self.DEFAULT_HEADERS,
            timeout=self._timeout,
            transport=transport,
        )

    def authenticate(self) -> str:
        """OAuth2 password grant → returns access_token.

        Uses the shared ``self._client`` (no transport parameter).
        After successful auth, stores the Bearer token on the client
        headers so all subsequent endpoint calls are authenticated.

        Returns:
            The access token string.

        Raises:
            AuthError: If credentials are invalid or the request fails.
        """
        try:
            resp = self._client.post(
                "/oauth/token",
                data={
                    "grant_type": "password",
                    "username": self._username,
                    "password": self._password,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            self._client.headers["Authorization"] = f"Bearer {self._access_token}"
            return self._access_token
        except httpx.HTTPStatusError as exc:
            raise AuthError(f"Auth failed ({exc.response.status_code})") from exc

    def fetch_library(self) -> list[dict]:
        """Fetch all books from the user's library, paginating automatically.

        Uses the shared ``self._client`` (no transport parameter).

        Returns:
            List of book dicts across all pages.

        Raises:
            AuthError: If not authenticated.
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        all_books: list[dict] = []
        next_url = "/api/v10/library"

        while next_url:
            resp = self._client.get(next_url)
            resp.raise_for_status()
            data = resp.json()
            all_books.extend(data.get("audiobooks", []))
            next_url = data.get("next_page") or None

        return all_books

    def fetch_m4b_url(self, isbn: str) -> str:
        """Fetch the M4B download URL for a given ISBN.

        Uses the shared ``self._client`` (no transport parameter).
        Rate-limited by the API semaphore.

        Args:
            isbn: The ISBN of the audiobook.

        Returns:
            The CDN URL string for the M4B file.

        Raises:
            AuthError: If not authenticated.
            M4BUnavailableError: If the book has no M4B format available (404).
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        with self._api_semaphore:
            resp = self._client.get(f"/api/v10/audiobooks/{isbn}/packaged_m4b")

            if resp.status_code == 404:
                raise M4BUnavailableError(f"M4B not available for ISBN {isbn}")

            resp.raise_for_status()
            data = resp.json()
            return data["m4b_url"]

    def fetch_download_manifest(self, isbn: str) -> dict:
        """Fetch the MP3 download manifest for a given ISBN.

        Uses the shared ``self._client`` (no transport parameter).
        Rate-limited by the API semaphore.

        Args:
            isbn: The ISBN of the audiobook.

        Returns:
            Dict with ``parts`` (list of {url, name}) and
            ``tracks`` (list of {number, chapter_title}).

        Raises:
            AuthError: If not authenticated.
            M4BUnavailableError: If the book has no MP3 format available (404).
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        with self._api_semaphore:
            resp = self._client.get("/api/v10/download-manifest", params={"isbn": isbn})

            if resp.status_code == 404:
                raise M4BUnavailableError(f"MP3 manifest not available for ISBN {isbn}")

            resp.raise_for_status()
            return resp.json()

    def fetch_pdf_extra_url(self, isbn: str, filename: str) -> str:
        """Fetch the PDF extra download URL for a given ISBN and filename.

        Uses the shared ``self._client`` (no transport parameter).
        Rate-limited by the API semaphore.

        Args:
            isbn: The ISBN of the audiobook.
            filename: The name of the PDF file to fetch.

        Returns:
            The CDN URL string for the PDF file.

        Raises:
            AuthError: If not authenticated.
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        with self._api_semaphore:
            resp = self._client.get(
                f"/api/v10/library/{isbn}/pdf_extra_url",
                params={"filename": filename},
            )

            resp.raise_for_status()
            data = resp.json()
            return data["pdf_url"]
