"""The shared popup keeps its form and control contracts without app services."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parents[1]


class PopupElements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.ids = {}
        self.forms = {}
        self.links = []
        self.labels = []
        self._form = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids[attrs["id"]] = (tag, attrs)
        if tag == "form":
            self._form = attrs["id"]
            self.forms[self._form] = {"attrs": attrs, "inputs": []}
        if tag == "input" and self._form:
            self.forms[self._form]["inputs"].append(attrs)
        if tag == "a":
            self.links.append(attrs)
        if tag == "label":
            self.labels.append(attrs)

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None


class HomeAuthPolishTests(unittest.TestCase):
    def setUp(self):
        env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                          autoescape=select_autoescape(["html"]))
        self.html = env.get_template("user/_auth_modal.html").render(
            session={"_csrf_token": "isolated-csrf"},
            next_url='/books?search_query=<script>alert(1)</script>')
        self.elements = PopupElements(self.html)

    def test_forms_keep_existing_post_routes_and_ajax_hooks(self):
        for form_id, route, mode, fields in (
            ("modalLoginForm", "/user/login", "login", {"email", "password"}),
            ("modalSignupForm", "/user/signup", "signup",
             {"first_name", "last_name", "username", "email", "password"}),
        ):
            form = self.elements.forms[form_id]
            self.assertEqual(form["attrs"]["action"], route)
            self.assertEqual(form["attrs"]["method"].lower(), "post")
            self.assertEqual(form["attrs"]["data-form"], mode)
            self.assertEqual(form["attrs"]["data-ajax"], "true")
            inputs = {field.get("name"): field for field in form["inputs"]}
            self.assertTrue(fields <= inputs.keys())
            self.assertEqual(inputs["_csrf_token"]["value"], "isolated-csrf")
            self.assertEqual(inputs["next_url"]["value"],
                             '/books?search_query=<script>alert(1)</script>')
            self.assertIn("auth-form", form["attrs"]["class"])
        self.assertNotIn("<script>", self.html)

    def test_existing_password_and_availability_ids_are_kept(self):
        for field_id in ("modalFirstName", "modalLastName", "modalUsername", "modalEmail",
                         "modalLoginPassword", "modalSignupPassword",
                         "modalLoginShowCheckbox", "modalSignupShowCheckbox", "modalFlash"):
            self.assertIn(field_id, self.elements.ids)
        for mode in ("Login", "Signup"):
            password = self.elements.ids[f"modal{mode}Password"][1]
            checkbox = self.elements.ids[f"modal{mode}ShowCheckbox"][1]
            self.assertEqual(password["type"], "password")
            self.assertIn(f"modal{mode}Password", checkbox["onchange"])

    def test_inputs_have_associated_labels_and_password_autocomplete(self):
        labeled = {label["for"] for label in self.elements.labels}
        for form in self.elements.forms.values():
            for field in form["inputs"]:
                if field["type"] != "hidden":
                    self.assertIn(field["id"], labeled)
        self.assertEqual(self.elements.ids["modalLoginPassword"][1]["autocomplete"],
                         "current-password")
        self.assertEqual(self.elements.ids["modalSignupPassword"][1]["autocomplete"],
                         "new-password")
        self.assertEqual(self.elements.ids["modalFlash"][1]["aria-live"], "polite")

    def test_existing_navigation_and_provider_routes_are_kept(self):
        links = {link["href"]: link for link in self.elements.links}
        for route in ("/user/login", "/user/signup", "/forgot-password", "/login/google",
                      "/login/github", "/login/facebook", "/privacy", "/terms",
                      "/data-deletion"):
            self.assertIn(route, links)
        self.assertIn("switchTab('signup')", links["/user/signup"]["onclick"])
        self.assertIn("switchTab('login')", links["/user/login"]["onclick"])

    def test_close_control_and_icons_do_not_depend_on_icon_font(self):
        self.assertEqual(self.elements.ids["authModal"][1]["aria-labelledby"],
                         "authModalTitle")
        self.assertIn('data-bs-dismiss="modal"', self.html)
        self.assertIn('aria-label="Close sign in"', self.html)
        self.assertGreaterEqual(self.html.count("<svg"), 12)
        self.assertNotIn('class="bi ', self.html)


if __name__ == "__main__":
    unittest.main()
