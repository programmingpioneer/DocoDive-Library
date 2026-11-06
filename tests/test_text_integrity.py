"""Public source must keep readable Unicode rather than damaged byte sequences."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
BROKEN=re.compile(r'\u00c3(?:[\u0080-\u00bf]|\u0192|\u02dc|\u203a)|\u00c2[\u0080-\u00bf]|[\u0080-\u009f]|\ufffd')

class TextIntegrityTests(unittest.TestCase):
    def test_active_public_source_and_lesson_unicode_are_readable(self):
        paths=list(ROOT.glob('*.py'))
        for folder,pattern in [('admin','*.py'),('templates','*.html'),('static/js','*.js'),('static/css','*.css')]:
            paths.extend((ROOT/folder).rglob(pattern))
        damaged=[str(path.relative_to(ROOT)) for path in paths if BROKEN.search(path.read_text(encoding='utf-8'))]
        self.assertEqual(damaged,[],'Damaged encoding in active source')
        lessons=(ROOT/'learning_content.py').read_text(encoding='utf-8')
        for text in ('π','≤','√','دنیا'):
            self.assertIn(text,lessons)

if __name__=='__main__':unittest.main()
