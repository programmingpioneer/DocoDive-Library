"""Loopback-only UI preview. Synthetic test data; never imports app.py or reads configuration."""
import ast
import sys
from pathlib import Path
from flask import render_template, session, redirect, url_for, jsonify
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_admin_studio import StudioTests
from seo import register_seo
case=StudioTests();case.setUp();app=case.app
app.config.update(UI_PREVIEW=True,DEBUG=False,SESSION_COOKIE_NAME='docodive_preview')
register_seo(app,case.svc)
app.jinja_env.filters['slugify']=lambda value:str(value).lower().replace(' ','-')
source=ast.parse((ROOT/'tests/test_admin_studio.py').read_text(encoding='utf-8'))
method=next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name=='test_public_pages_render_metadata_and_javascript')
context={}
for n in method.body:
    if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('book','context'):
        exec(compile(ast.Module(body=[n],type_ignores=[]),'preview-context','exec'),context)
values=context['context']
@app.get('/preview/studio')
def preview_studio():
    session.update(studio_user_id=1,studio_token='test-session')
    return redirect(url_for('admin.admin_dashboard'))
@app.get('/preview/public')
def preview_public():
    session.pop('user_id',None)
    return redirect('/')
app.view_functions['home']=lambda:render_template('user/index.html',**values)
app.view_functions['user_login']=lambda:render_template('user/auth.html',mode='login')
app.view_functions['user_signup']=lambda:render_template('user/auth.html',mode='signup')
@app.get('/preview/verify')
def preview_verify():return render_template('admin/admin_verify.html')
labels=['Registered users','Books','Awaiting approval','Pending deletions','Active members · 30d','Reviews','Comments','Suggestions']
endpoints=['admin.list_users','admin.admin_books_list','admin.pending_books','admin.pending_deletions','admin.tracking','admin.moderation_panel','admin.moderation_panel','admin.suggestions_manage']
def insights():
    charts=[]
    for title,vals in [('Daily active signed-in members',[12,18,15,27,32,28,41]),('Page responses · guests + members',[110,142,121,180,205,198,246]),('Review volume',[3,7,4,8,6,10,12]),('Suggestion volume',[1,2,0,4,2,3,5])]:
        charts.append(dict(title=title,type='line',labels=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],values=vals,links=[url_for('admin.tracking')]*7))
    return jsonify(cards=[dict(label=l,value=v,url=url_for(e)) for l,v,e in zip(labels,[128,328,9,2,41,64,102,18],endpoints)],charts=charts,note='UI preview uses synthetic data. No real database or services are connected.')
app.view_functions['admin.insights_api']=insights
if __name__=='__main__':
    print('Synthetic UI preview: http://127.0.0.1:5011 | no real database/email/configuration')
    app.run(host='127.0.0.1',port=5011,use_reloader=False,debug=False,load_dotenv=False)
