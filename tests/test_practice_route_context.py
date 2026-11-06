"""Exercise the real explicit practice entry point without configured services."""
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader
import learning_content
from test_security_regressions import load_function

ROOT = Path(__file__).resolve().parents[1]


class PracticeRouteContextTests(unittest.TestCase):
    def test_explicit_python_route_renders_shared_wayfinding_and_resources(self):
        base = """{% block title %}{% endblock %}{% block meta_description %}{% endblock %}
        {% block extra_css %}{% endblock %}{% block content %}{% endblock %}
        {% block scripts %}{% endblock %}"""
        env = Environment(loader=ChoiceLoader([
            DictLoader({'user/base.html': base}), FileSystemLoader(ROOT / 'templates')]),
            autoescape=True)
        env.globals.update(url_for=lambda endpoint, **kw: '/static/' + kw.get('filename', ''),
                           request=SimpleNamespace(path='/learn/python/practice',
                                                   base_url='https://example.test/learn/python/practice',
                                                   host_url='https://example.test/'))
        scope = dict(vars(learning_content), render_template=lambda name, **ctx:
                     env.get_template(name).render(**ctx))
        html = load_function('python_practice', scope)()
        self.assertIn('aria-current="page">Practice Resources', html)
        self.assertIn('/learn/python/practice" aria-current="page"', html)
        self.assertIn('Choose your practice session', html)
        self.assertIn('Keep learning Python', html)
        self.assertNotIn('Undefined', html)


if __name__ == '__main__':
    unittest.main()
