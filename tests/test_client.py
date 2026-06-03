"""Tests for librofm_downloader.client — TDD vertical slices."""

import json
import logging

import httpx
import pytest

from librofm_downloader.client import LibroFmClient, AuthError, M4BUnavailableError


class TestAuthenticate:
    """OAuth2 password grant authentication."""

    def test_returns_access_token_on_valid_credentials(self):
        """Valid username/password → access_token returned."""
        client = LibroFmClient(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        def token_handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/oauth/token"
            return httpx.Response(
                200,
                json={"access_token": "tok_abc123", "token_type": "bearer", "expires_in": 7200},
            )

        transport = httpx.MockTransport(token_handler)
        token = client.authenticate(transport=transport)

        assert token == "tok_abc123"

    def test_raises_auth_error_on_invalid_credentials(self):
        """Wrong password → AuthError with descriptive message."""
        client = LibroFmClient(
            base_url="https://libro.fm",
            username="alice",
            password="wrongpass",
        )

        def token_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_grant"})

        transport = httpx.MockTransport(token_handler)

        with pytest.raises(AuthError, match="Auth failed") as exc_info:
            client.authenticate(transport=transport)

        assert "401" in str(exc_info.value)

    def test_sends_required_headers_with_auth_request(self):
        """X-LibroFm-AppVer and User-Agent headers must be present."""
        client = LibroFmClient(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        headers_captured: dict[str, str] = {}

        def token_handler(request: httpx.Request) -> httpx.Response:
            headers_captured.update(dict(request.headers))
            return httpx.Response(
                200,
                json={"access_token": "tok_abc123", "token_type": "bearer", "expires_in": 7200},
            )

        transport = httpx.MockTransport(token_handler)
        client.authenticate(transport=transport)

        assert headers_captured["x-librofm-appver"] == "7.34.8"
        assert headers_captured["user-agent"] == "okhttp/5.3.2"


class TestFetchLibrary:
    """Paginated library fetch — GET /api/v10/library."""

    def test_returns_books_on_single_page(self):
        """Single-page library returns all books, no pagination loop."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)
        result = client.fetch_library(transport=transport)

        assert len(result) == 1
        assert result[0]["isbn"] == "9781234567890"

    def test_paginates_through_all_pages(self):
        """Multi-page library: follows next_page until exhausted."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)
        result = client.fetch_library(transport=transport)

        assert len(result) == 3
        assert result[0]["isbn"] == "978111"
        assert result[1]["isbn"] == "978222"
        assert result[2]["isbn"] == "978333"

    def test_raises_auth_error_if_not_authenticated(self):
        """Calling fetch_library before authenticate → clear error."""
        client = LibroFmClient(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        with pytest.raises(AuthError, match="Not authenticated"):
            client.fetch_library()



class TestFetchM4BUrl:
    """M4B download URL lookup — GET /api/v10/audiobooks/{isbn}/packaged_m4b."""

    def test_returns_download_url_when_m4b_available(self):
        """Book with M4B format available → returns CDN URL string."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)
        url = client.fetch_m4b_url("9781234567890", transport=transport)

        assert url == "https://cdn.libro.fm/audiobooks/9781234567890.m4b"

    def test_raises_m4b_unavailable_on_404(self):
        """Book without M4B format → raises M4BUnavailableError."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)

        with pytest.raises(M4BUnavailableError, match="M4B not available for ISBN 9780000000001"):
            client.fetch_m4b_url("9780000000001", transport=transport)


# ---------------------------------------------------------------------------
# MP3 download manifest — Issue #6
# ---------------------------------------------------------------------------


class TestFetchDownloadManifest:
    """MP3 download manifest — GET /api/v10/download-manifest?isbn=."""

    def test_returns_parts_and_tracks_when_available(self):
        """Book with MP3 format → returns parts list and track metadata."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)
        manifest = client.fetch_download_manifest("9781234567890", transport=transport)

        assert len(manifest["parts"]) == 2
        assert manifest["parts"][0]["url"] == "https://cdn.libro.fm/part1.zip"
        assert manifest["parts"][1]["url"] == "https://cdn.libro.fm/part2.zip"
        assert len(manifest["tracks"]) == 2
        assert manifest["tracks"][0]["chapter_title"] == "Chapter 1"

    def test_returns_empty_parts_when_no_mp3_available(self):
        """Book without MP3 format → returns empty manifest (404 or empty)."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)

        with pytest.raises(M4BUnavailableError):
            client.fetch_download_manifest("9780000000001", transport=transport)


# ---------------------------------------------------------------------------
# PDF extra download URL — Issue #7
# ---------------------------------------------------------------------------


class TestFetchPdfExtraUrl:
    """PDF extra download URL — GET /api/v10/library/{isbn}/pdf_extra_url?filename=."""

    def test_returns_pdf_url_when_available(self):
        """Book with PDF extra available → returns CDN URL string."""
        client = LibroFmClient(
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
        client.authenticate(transport=transport)
        url = client.fetch_pdf_extra_url("9781234567890", "map.pdf", transport=transport)

        assert url == "https://cdn.libro.fm/pdf/9781234567890/map.pdf"

    def test_raises_auth_error_if_not_authenticated(self):
        """Calling fetch_pdf_extra_url before authenticate → clear error."""
        client = LibroFmClient(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
        )

        with pytest.raises(AuthError, match="Not authenticated"):
            client.fetch_pdf_extra_url("9781234567890", "map.pdf")
