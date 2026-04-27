from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.core.ports import IAuthProvider


class TestStaticTokenAuth:
    def test_implements_interface(self):
        auth = StaticTokenAuth("tok-123")
        assert isinstance(auth, IAuthProvider)

    def test_get_token(self):
        auth = StaticTokenAuth("tok-123")
        assert auth.get_token() == "tok-123"

    def test_is_valid_with_token(self):
        auth = StaticTokenAuth("tok-123")
        assert auth.is_valid() is True

    def test_is_valid_empty(self):
        auth = StaticTokenAuth("")
        assert auth.is_valid() is False

    def test_refresh_is_noop(self):
        auth = StaticTokenAuth("tok-123")
        auth.refresh()
        assert auth.get_token() == "tok-123"
