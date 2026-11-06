"""Render public/lesson fixture states without configured services or browser claims."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from reader_ui_preview import app,PAGES

root=Path(__file__).resolve().parents[1]
paths=['/']+['/preview/page/'+name for name in PAGES]
paths += ['/preview/lesson/'+p.parent.name+'/'+p.stem for p in (root/'templates/user').glob('*/*.html') if p.parent.name!='learn_universal']
results=[]
scripts=[]
with app.test_client() as client:
    for path in paths:
        response=client.get(path)
        html=response.get_data(as_text=True)
        for index,(attrs,source) in enumerate(re.findall(r'<script([^>]*)>(.*?)</script>',html,re.S)):
            if 'src=' in attrs:continue
            if 'application/ld+json' in attrs or 'application/json' in attrs:
                json.loads(source)
            else:scripts.append(dict(name=f'{path} inline {index}',source=source))
        results.append(dict(path=path,status=response.status_code,theme='theme-init.js' in html and 'css/theme.css' in html,
                            home_scope=path!='/' or 'data-page-home="true"' in html,skeleton='page-skeleton-shell' in html,error='Traceback (most recent call last)' in html))
template_count=0
for template in (root/'templates').rglob('*.html'):
    app.jinja_env.parse(template.read_text(encoding='utf-8'))
    template_count+=1
static_scripts=list((root/'static/js').glob('*.js'))+[root/'static/sw.js']
scripts.extend(dict(name=str(path.relative_to(root)),source=path.read_text(encoding='utf-8')) for path in static_scripts)
check=subprocess.run([shutil.which('node'),'-e',"const fs=require('node:fs'),vm=require('node:vm');const scripts=JSON.parse(fs.readFileSync(0,'utf8'));for(const item of scripts)new vm.Script(item.source,{filename:item.name});console.log(scripts.length+' scripts parsed without execution');"],
                     input=json.dumps(scripts),text=True,capture_output=True,timeout=40)
if check.returncode:raise RuntimeError(check.stderr)
output=root/'deliverables/ui-token-refinement/render-audit.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(dict(scope='Synthetic Flask render and source parse only; no configured app or external services.',
                                 template_count=template_count,static_script_count=len(static_scripts),rendered_inline_script_count=len(scripts)-len(static_scripts),results=results),indent=2)+'\n',encoding='utf-8')
failed=[r for r in results if r['status']!=200 or not r['theme'] or not r['skeleton'] or not r['home_scope'] or r['error']]
print(f'{len(results)} synthetic public/lesson renders; {len(failed)} failures.')
print(f'{template_count} Jinja templates parsed; {len(static_scripts)} static scripts and {len(scripts)-len(static_scripts)} rendered inline scripts parsed without execution.')
for row in failed:print(row)
raise SystemExit(bool(failed))
