"""Local-only checks: execute selected functions without importing app/config."""

import ast
import pathlib
import secrets
import types
import unittest
import hmac

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_function(name, scope):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "isolated-app", "exec"), scope)
    return scope[name]


class SecurityRegressionTests(unittest.TestCase):
    def canonical(self, production, host, scheme="http"):
        scope = dict(
            IS_PRODUCTION=production,
            request=types.SimpleNamespace(
                host=host, scheme=scheme, url=f"{scheme}://{host}/books?page=2"
            ),
            redirect=lambda url, code: (url, code),
        )
        return load_function("enforce_canonical_host", scope)()

    def test_development_lan_does_not_redirect_to_https(self):
        for host in (
            "192.168.1.9:5000",
            "127.0.0.1:5000",
            "localhost:5000",
            "10.0.0.2:5000",
        ):
            self.assertIsNone(self.canonical(False, host))

    def test_production_still_redirects_http_to_https(self):
        self.assertEqual(
            self.canonical(True, "library.example"),
            ("https://library.example/books?page=2", 301),
        )
        self.assertIsNone(self.canonical(True, "library.example", "https"))

    def csrf(self, headers, form, session):
        def abort(code):
            raise PermissionError(code)

        scope = dict(
            request=types.SimpleNamespace(
                path="/user/favorite/1", method="POST", headers=headers, form=form
            ),
            session=session,
            abort=abort,
            secrets=secrets,
            hmac=hmac,
        )
        return load_function("csrf_protect", scope)()

    def test_ajax_header_does_not_bypass_csrf(self):
        with self.assertRaises(PermissionError):
            self.csrf({"X-Requested-With": "XMLHttpRequest"}, {}, {})

    def test_matching_form_token_accepted(self):
        self.csrf({}, {"_csrf_token": "token"}, {"_csrf_token": "token"})

    def test_matching_header_token_accepted(self):
        self.csrf({"X-CSRF-Token": "token"}, {}, {"_csrf_token": "token"})

    def test_wrong_header_token_rejected(self):
        with self.assertRaises(PermissionError):
            self.csrf({"X-CSRF-Token": "wrong"}, {}, {"_csrf_token": "token"})

    def test_google_callback_rejects_missing_or_wrong_state_before_network(self):
        for state, returned in [
            ({}, "attacker"),
            ({"google_oauth_state": "expected"}, "attacker"),
        ]:
            scope = dict(
                request=types.SimpleNamespace(
                    args={"state": returned, "code": "unused"}
                ),
                session=state,
                hmac=hmac,
                flash=lambda *args: None,
                redirect=lambda url: url,
                url_for=lambda endpoint: endpoint,
            )
            self.assertEqual(load_function("google_callback", scope)(), "user_login")
            self.assertNotIn("google_oauth_state", state)

    def test_reader_logout_preserves_studio_identity(self):
        state = {
            "user_id": 2,
            "user_name": "reader",
            "studio_user_id": 1,
            "_csrf_token": "token",
        }
        scope = dict(
            session=state,
            flash=lambda *args: None,
            redirect=lambda url: url,
            url_for=lambda endpoint: endpoint,
        )
        load_function("user_logout", scope)()
        self.assertNotIn("user_id", state)
        self.assertEqual(state["studio_user_id"], 1)


if __name__ == "__main__":
    unittest.main()
