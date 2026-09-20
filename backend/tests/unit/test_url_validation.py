"""Unit tests for URL validation in business profile."""

import pytest

from app.api.v1.businesses import _validate_url
from app.exceptions import ValidationError


class TestURLValidation:
    """Test URL validation for social links and images."""

    def test_valid_https_url(self):
        _validate_url("https://example.com")

    def test_valid_http_url(self):
        _validate_url("http://example.com")

    def test_valid_url_with_path(self):
        _validate_url("https://example.com/page/sub")

    def test_valid_url_with_port(self):
        _validate_url("https://example.com:8080/path")

    def test_valid_url_with_subdomain(self):
        _validate_url("https://www.facebook.com/mybusiness")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(ValidationError):
            _validate_url("javascript:alert(1)")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValidationError):
            _validate_url("ftp://files.example.com/doc")

    def test_rejects_data_scheme(self):
        with pytest.raises(ValidationError):
            _validate_url("data:text/html,<script>alert(1)</script>")

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            _validate_url("")

    def test_rejects_no_scheme(self):
        with pytest.raises(ValidationError):
            _validate_url("example.com/page")

    def test_rejects_malformed_url(self):
        with pytest.raises(ValidationError):
            _validate_url("https://")

    def test_rejects_bare_text(self):
        with pytest.raises(ValidationError):
            _validate_url("not a url")
