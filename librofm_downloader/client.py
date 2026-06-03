"""HTTP client for Libro.fm API — auth and library fetch."""

import httpx


class AuthError(Exception):
    """Authentication failed (bad credentials, network error, etc.)."""


class M4BUnavailableError(Exception):
    """M4B format is not available for this book (404 from API)."""


class LibroFmClient:
    """Libro.fm API client with OAuth2 password grant and library fetching."""

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
    ):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._access_token: str | None = None

    def authenticate(self, transport: httpx.BaseTransport | None = None) -> str:
        """OAuth2 password grant → returns access_token.

        Args:
            transport: Optional httpx transport override for testing.

        Returns:
            The access token string.

        Raises:
            AuthError: If credentials are invalid or the request fails.
        """
        client = httpx.Client(
            base_url=self._base_url,
            headers=self.DEFAULT_HEADERS,
            timeout=self._timeout,
            transport=transport,
        )

        try:
            resp = client.post(
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
            return self._access_token
        except httpx.HTTPStatusError as exc:
            raise AuthError(f"Auth failed ({exc.response.status_code})") from exc

    def fetch_library(self, transport: httpx.BaseTransport | None = None) -> list[dict]:
        """Fetch all books from the user's library, paginating automatically.

        Args:
            transport: Optional httpx transport override for testing.

        Returns:
            List of book dicts across all pages.

        Raises:
            AuthError: If not authenticated.
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        headers = {**self.DEFAULT_HEADERS, "Authorization": f"Bearer {self._access_token}"}
        all_books: list[dict] = []

        client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=transport,
        )

        next_url = "/api/v10/library"
        while next_url:
            resp = client.get(next_url)
            resp.raise_for_status()
            data = resp.json()
            all_books.extend(data.get("audiobooks", []))
            next_url = data.get("next_page") or None

        return all_books


    def fetch_m4b_url(self, isbn: str, transport: httpx.BaseTransport | None = None) -> str:
        """Fetch the M4B download URL for a given ISBN.

        Args:
            isbn: The ISBN of the audiobook.
            transport: Optional httpx transport override for testing.

        Returns:
            The CDN URL string for the M4B file.

        Raises:
            AuthError: If not authenticated.
            M4BUnavailableError: If the book has no M4B format available (404).
        """
        if not self._access_token:
            raise AuthError("Not authenticated. Call authenticate() first.")

        headers = {**self.DEFAULT_HEADERS, "Authorization": f"Bearer {self._access_token}"}

        client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=transport,
        )

        resp = client.get(f"/api/v10/audiobooks/{isbn}/packaged_m4b")

        if resp.status_code == 404:
            raise M4BUnavailableError(f"M4B not available for ISBN {isbn}")

        resp.raise_for_status()
        data = resp.json()
        return data["m4b_url"]
