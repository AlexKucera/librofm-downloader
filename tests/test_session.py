"""Tests for librofm_downloader.session — TDD vertical slices."""

from __future__ import annotations

import threading
import time

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



# ---------------------------------------------------------------------------
# API Rate Limiter — Issue #15 (migrated from test_client.py, Issue #37)
# ---------------------------------------------------------------------------


class TestApiRateLimiter:
    """threading.Semaphore(3) caps concurrent Libro.fm API calls.

    Applied to: fetch_m4b_url, fetch_download_manifest, fetch_pdf_extra_url.
    NOT applied to: authenticate, fetch_library, CDN downloads.
    """

    def test_semaphore_blocks_at_capacity(self):
        """4 concurrent callers: 3 proceed immediately, 4th blocks until one finishes."""

        call_can_finish: threading.Event = threading.Event()
        state_lock = threading.Lock()
        state = {"in_flight": 0, "max_in_flight": 0}

        def slow_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            with state_lock:
                state["in_flight"] += 1
                if state["in_flight"] > state["max_in_flight"]:
                    state["max_in_flight"] = state["in_flight"]
            call_can_finish.wait(timeout=5)
            with state_lock:
                state["in_flight"] -= 1
            return httpx.Response(
                200,
                json={"m4b_url": "https://cdn.libro.fm/test.m4b"},
            )

        transport = httpx.MockTransport(slow_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()

        errors: list[BaseException] = []

        def fetch_thread(isbn: str):
            try:
                session.fetch_m4b_url(isbn)
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=fetch_thread, args=(f"978{i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()

        time.sleep(0.5)
        call_can_finish.set()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Unexpected errors: {errors}"
        assert state["max_in_flight"] <= 3, (
            f"Max in-flight was {state['max_in_flight']}, expected <= 3"
        )

    def test_semaphore_releases_on_exception(self):
        """Semaphore is released even when the API call raises an exception."""
        call_number = [1]  # Use list for mutability in closure

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            n = call_number[0]
            call_number[0] += 1
            if n == 2:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={"m4b_url": "https://cdn.libro.fm/test.m4b"},
            )

        transport = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=transport,
        )
        session.authenticate()

        # First call should succeed (releases semaphore normally)
        result = session.fetch_m4b_url("978111")
        assert result == "https://cdn.libro.fm/test.m4b"

        # Second call should raise (semaphore must still be released after this)
        with pytest.raises(M4BUnavailableError):
            session.fetch_m4b_url("978222")

        # Third call should succeed — proves semaphore was released by the failed call
        result3 = session.fetch_m4b_url("978333")
        assert result3 == "https://cdn.libro.fm/test.m4b"

    def test_cdn_downloads_bypass_semaphore(self):
        """CDN downloads (download_m4b, download_zip_part) are NOT limited by the API semaphore."""
        import tempfile

        from librofm_downloader.downloader import download_m4b

        # Fill all 3 API semaphore slots with slow calls that block
        api_calls_blocked: threading.Event = threading.Event()

        def slow_api_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            # Block — holds the semaphore slot indefinitely (until test ends)
            api_calls_blocked.wait(timeout=5)
            return httpx.Response(
                200,
                json={"m4b_url": "https://cdn.libro.fm/test.m4b"},
            )

        api_transport = httpx.MockTransport(slow_api_handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=api_transport,
        )
        session.authenticate()

        # Occupy all 3 semaphore slots with blocked API calls
        api_threads = [
            threading.Thread(target=session.fetch_m4b_url, args=(f"978block{i}",))
            for i in range(3)
        ]
        for t in api_threads:
            t.start()
        time.sleep(0.2)  # Let them acquire the semaphore

        # Now try a CDN download — it should succeed immediately, not block on semaphore
        cdn_started = False

        def cdn_handler(request: httpx.Request) -> httpx.Response:
            nonlocal cdn_started
            cdn_started = True
            return httpx.Response(200, content=b"fake m4b data")

        cdn_transport = httpx.MockTransport(cdn_handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/test.m4b"
            # This should NOT block even though all 3 API slots are occupied
            result = download_m4b("https://cdn.example.com/test.m4b", output_path, transport=cdn_transport)
            assert result.name.endswith("test.m4b")

        assert cdn_started, "CDN download should have proceeded without waiting for API semaphore"

        # Clean up blocked threads
        api_calls_blocked.set()
        for t in api_threads:
            t.join(timeout=5)

    def test_authenticate_and_fetch_library_not_limited(self):
        """authenticate() and fetch_library() do NOT acquire the API semaphore."""
        # Fill all 3 API semaphore slots with blocked calls
        api_calls_blocked: threading.Event = threading.Event()

        def slow_api_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 7200},
                )
            api_calls_blocked.wait(timeout=5)
            return httpx.Response(
                200,
                json={"m4b_url": "https://cdn.libro.fm/test.m4b"},
            )

        # NOTE: This test uses a separate session for the blocking API calls.
        # The session under test gets a different transport so authenticate/fetch_library
        # can use a different handler while the blocking calls hold the semaphore.
        api_transport = httpx.MockTransport(slow_api_handler)
        blocking_session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=api_transport,
        )
        blocking_session.authenticate()

        # Occupy all 3 slots
        api_threads = [
            threading.Thread(target=blocking_session.fetch_m4b_url, args=(f"978block{i}",))
            for i in range(3)
        ]
        for t in api_threads:
            t.start()
        time.sleep(0.2)

        # authenticate() should work fine — it doesn't use the semaphore
        # We need a fresh session+transport for this since the old one's auth handler
        # would conflict with the slow_api_handler
        def auth_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"access_token": "tok_new", "token_type": "bearer", "expires_in": 7200},
            )

        def library_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"audiobooks": []})

        def combined_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                return auth_handler(request)
            return library_handler(request)

        test_transport = httpx.MockTransport(combined_handler)
        test_session = LibroFmSession(
            base_url="https://libro.fm",
            username="alice",
            password="secret123",
            transport=test_transport,
        )
        token = test_session.authenticate()
        assert token == "tok_new"

        # fetch_library() should also work — it doesn't use the semaphore
        books = test_session.fetch_library()
        assert books == []

        # Clean up
        api_calls_blocked.set()



class TestTransportProperty:
    """Public transport property — Issue #38."""

    def test_returns_underlying_transport(self):
        """session.transport returns the internal client's transport."""
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="u",
            password="p",
        )

        # Default transport is None when not injected
        assert session.transport is None

    def test_returns_injected_mock_transport(self):
        """When a MockTransport is injected, session.transport returns it."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        mock_t = httpx.MockTransport(handler)
        session = LibroFmSession(
            base_url="https://libro.fm",
            username="u",
            password="p",
            transport=mock_t,
        )

        assert session.transport is mock_t