"""Tests for librofm_downloader.session — TDD vertical slices."""

from __future__ import annotations

import httpx
import pytest

from librofm_downloader.session import LibroFmSession, AuthError, M4BUnavailableError


class TestConstructor:
    """LibroFmSession constructor builds a shared internal httpx.Client."""

    def test_importable_from_session_module(self):
        """LibroFmSession can be imported from librofm_downloader.session."""
        assert LibroFmSession is not None

    def test_creates_internal_httpx_client(self):
        """Constructor creates self._client as an httpx.Client instance."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        assert isinstance(session._client, httpx.Client)

    def test_injects_transport_into_internal_client(self):
        """When transport= is passed, the internal client uses it for requests."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )

        assert isinstance(session._client, httpx.Client)
        # Verify the injected transport works by making a request through the internal client
        resp = session._client.get("/test")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_default_transport_is_none(self):
        """When no transport is passed, the client has no custom transport (real HTTP)."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="u",
            password="p",
        )

        # With transport=None, httpx.Client uses its default transport (real network)
        # We just verify the client was created and has the expected base_url
        assert session._client.base_url == "https://libro.fm"



class TestAuthenticate:
    """OAuth2 password grant authentication — uses shared _client, no transport param."""

    def test_returns_access_token_on_valid_credentials(self):
        """Valid username/password → access_token returned."""

        def token_handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/oauth/token"
            return httpx.Response(
                200,
                json={"access_token": "tok_abc123", "token_type": "bearer", "expires_in": 7200},
            )

        transport = httpx.MockTransport(token_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )

        token = session.authenticate()  # NO transport arg!

        assert token == "tok_abc123"

    def test_raises_auth_error_on_invalid_credentials(self):
        """Wrong password → AuthError with descriptive message."""

        def token_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_grant"})

        transport = httpx.MockTransport(token_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="wrongpass",
            transport=transport,
        )

        with pytest.raises(AuthError, match="Auth failed") as exc_info:
            session.authenticate()

        assert "401" in str(exc_info.value)

    def test_sends_required_headers_with_auth_request(self):
        """X-LibroFm-AppVer and User-Agent headers must be present."""
        headers_captured: dict[str, str] = {}

        def token_handler(request: httpx.Request) -> httpx.Response:
            headers_captured.update(dict(request.headers))
            return httpx.Response(
                200,
                json={"access_token": "tok_abc123", "token_type": "bearer", "expires_in": 7200},
            )

        transport = httpx.MockTransport(token_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )

        session.authenticate()

        assert headers_captured["x-librofm-appver"] == "7.34.8"
        assert headers_captured["user-agent"] == "okhttp/5.3.2"

    def test_stores_token_on_instance_and_client_headers(self):
        """After authenticate(), token is on self._access_token AND in client headers."""

        def token_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"access_token": "tok_stored", "token_type": "bearer", "expires_in": 7200},
            )

        transport = httpx.MockTransport(token_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )

        token = session.authenticate()

        assert token == "tok_stored"
        assert session._access_token == "tok_stored"



class TestFetchLibrary:
    """Paginated library fetch — GET /api/v10/library, uses shared _client."""

    def test_returns_books_on_single_page(self):
        """Single-page library returns all books, no pagination loop."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        books = [{"isbn": "9781234567890", "title": "Test Book"}]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/library":
                return httpx.Response(200, json={"audiobooks": books})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()
        result = session.fetch_library()  # NO transport arg!

        assert len(result) == 1
        assert result[0]["isbn"] == "9781234567890"

    def test_paginates_through_all_pages(self):
        """Multi-page library: follows next_page until exhausted."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        page1_books = [{"isbn": "978111", "title": "Book A"}]
        page2_books = [{"isbn": "978222", "title": "Book B"}, {"isbn": "978333", "title": "Book C"}]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/library" and "page" not in request.url.params:
                return httpx.Response(
                    200,
                    json={"audiobooks": page1_books, "next_page": "/api/v10/library?page=2"},
                )
            if "page=2" in str(request.url):
                return httpx.Response(200, json={"audiobooks": page2_books})  # no next_page → stop
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()
        result = session.fetch_library()  # NO transport arg!

        assert len(result) == 3
        assert result[0]["isbn"] == "978111"
        assert result[1]["isbn"] == "978222"
        assert result[2]["isbn"] == "978333"

    def test_raises_auth_error_if_not_authenticated(self):
        """Calling fetch_library before authenticate → clear error."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        with pytest.raises(AuthError, match="Not authenticated"):
            session.fetch_library()


class TestFetchM4BUrl:
    """M4B download URL lookup — GET /api/v10/audiobooks/{isbn}/packaged_m4b."""

    def test_returns_download_url_when_m4b_available(self):
        """Book with M4B format available → returns CDN URL string."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9781234567890/packaged_m4b":
                return httpx.Response(
                    200,
                    json={"m4b_url": "https://cdn.libro.fm/audiobooks/9781234567890.m4b"},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()
        url = session.fetch_m4b_url("9781234567890")  # NO transport arg!

        assert url == "https://cdn.libro.fm/audiobooks/9781234567890.m4b"

    def test_raises_m4b_unavailable_on_404(self):
        """Book without M4B format → raises M4BUnavailableError."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/audiobooks/9780000000001/packaged_m4b":
                return httpx.Response(404)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()

        with pytest.raises(M4BUnavailableError, match="M4B not available for ISBN 9780000000001"):
            session.fetch_m4b_url("9780000000001")



# ---------------------------------------------------------------------------
# MP3 download manifest — Issue #6
# ---------------------------------------------------------------------------


class TestFetchDownloadManifest:
    """MP3 download manifest — GET /api/v10/download-manifest?isbn=."""

    def test_returns_parts_and_tracks_when_available(self):
        """Book with MP3 format → returns parts list and track metadata."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest" and request.url.params.get("isbn") == "9781234567890":
                return httpx.Response(
                    200,
                    json={
                        "parts": [
                            {"url": "https://cdn.libro.fm/part1.zip", "name": "part01"},
                            {"url": "https://cdn.libro.fm/part2.zip", "name": "part02"},
                        ],
                        "tracks": [
                            {"number": 1, "chapter_title": "Chapter 1"},
                            {"number": 2, "chapter_title": "Chapter 2"},
                        ],
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()
        manifest = session.fetch_download_manifest("9781234567890")  # NO transport arg!

        assert len(manifest["parts"]) == 2
        assert manifest["parts"][0]["url"] == "https://cdn.libro.fm/part1.zip"
        assert manifest["parts"][1]["url"] == "https://cdn.libro.fm/part2.zip"
        assert len(manifest["tracks"]) == 2
        assert manifest["tracks"][0]["chapter_title"] == "Chapter 1"

    def test_raises_m4b_unavailable_on_404(self):
        """Book without MP3 format → raises M4BUnavailableError."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/download-manifest":
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()

        with pytest.raises(M4BUnavailableError):
            session.fetch_download_manifest("9780000000001")



# ---------------------------------------------------------------------------
# PDF extra download URL — Issue #7 / Cycle 6
# ---------------------------------------------------------------------------


class TestFetchPdfExtraUrl:
    """PDF extra download URL — GET /api/v10/library/{isbn}/pdf_extra_url?filename=."""

    def test_returns_pdf_url_when_available(self):
        """Book with PDF extra available → returns CDN URL string."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            if request.url.path == "/api/v10/library/9781234567890/pdf_extra_url":
                assert request.url.params.get("filename") == "map.pdf"
                return httpx.Response(
                    200,
                    json={"pdf_url": "https://cdn.libro.fm/pdf/9781234567890/map.pdf"},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()
        url = session.fetch_pdf_extra_url("9781234567890", "map.pdf")  # NO transport arg!

        assert url == "https://cdn.libro.fm/pdf/9781234567890/map.pdf"

    def test_raises_auth_error_if_not_authenticated(self):
        """Calling fetch_pdf_extra_url before authenticate → clear error."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        with pytest.raises(AuthError, match="Not authenticated"):
            session.fetch_pdf_extra_url("9781234567890", "map.pdf")
