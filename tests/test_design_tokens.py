"""Palette checks protect actual text/control contrast in both appearances."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

def luminance(color):
    values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))

def contrast(a,b):
    hi,lo=sorted((luminance(a),luminance(b)),reverse=True)
    return (hi+.05)/(lo+.05)

class DesignTokenTests(unittest.TestCase):
    def test_text_and_primary_control_contrast_in_both_modes(self):
        source=(ROOT/'static/css/tokens.css').read_text(encoding='utf-8')
        blocks=re.findall(r'(?:^|\n)(:root|html\[data-bs-theme=dark\])\s*\{([^}]+)\}',source)
        self.assertEqual(len(blocks),2)
        for mode,body in blocks:
            colors=dict(re.findall(r'(--ui-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;',body))
            for ink in ('--ui-text','--ui-muted','--ui-accent'):
                for surface in ('--ui-bg','--ui-surface','--ui-surface-alt'):
                    with self.subTest(mode=mode,ink=ink,surface=surface):
                        self.assertGreaterEqual(contrast(colors[ink],colors[surface]),4.5)
            self.assertGreaterEqual(contrast(colors['--ui-on-primary'],colors['--ui-primary']),4.5)
            self.assertGreaterEqual(contrast(colors['--ui-on-primary'],colors['--ui-primary-hover']),4.5)

    def test_status_and_code_text_contrast(self):
        source=(ROOT/'static/css/tokens.css').read_text(encoding='utf-8')
        for mode,body in re.findall(r'(?:^|\n)(:root|html\[data-bs-theme=dark\])\s*\{([^}]+)\}',source):
            colors=dict(re.findall(r'(--ui-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;',body))
            for role in ('success','warning','danger'):
                for surface in ('--ui-surface','--ui-'+role+'-soft'):
                    with self.subTest(mode=mode,role=role,surface=surface):
                        self.assertGreaterEqual(contrast(colors['--ui-'+role],colors[surface]),4.5)
            self.assertGreaterEqual(contrast(colors['--ui-code-text'],colors['--ui-code-bg']),4.5)

if __name__=='__main__':unittest.main()
