"""Disposable reader UI fixtures. No app.py import, credentials, email or database."""
import sys
from pathlib import Path
from datetime import datetime
from io import BytesIO
from flask import render_template, render_template_string, session, redirect, abort, request, jsonify, flash, send_file, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_preview import app, values
from public_presentation import community_display_count, homepage_review_cards
from community_presentation import achievement_summary, rank_leaders

app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True
sample_book = dict(values['book'], title='A practical handbook for programming and reliable systems',
                   author='A reader with a long display name', avg_rating=4.5, downloaded_at='2026-10-31 12:00')
samples = [dict(sample_book, id=i, title=t, image_url=cover) for i, t, cover in [
    (4, sample_book['title'], None),
    (5, 'Short title', '/static/images/docoDive-og.jpg'),
    (6, 'An exceptionally long title that should wrap consistently without moving any other controls', None),
]]
values.update(pdfs=samples, books=samples, recommended_books=samples,
              monthly_users=2, total_books=3, total_categories=1,
              community_counter=community_display_count(2), review_cards=homepage_review_cards([]))
values.update(related_books=samples, trending_books=samples)

PAGES = {
    'settings':'account_settings','deletion':'account_deletion','profile':'user_profile',
    'edit-profile':'edit_profile','stats':'user_stats','preferences':'preferences',
    'notifications':'notifications','favorites':'user_favorites','history':'user_history',
    'upload':'user_upload','books':'books','home':'index','detail':'book_detail',
    'reviews':'reviews','feedback':'feedback','leaderboard':'leaderboard',
    'login':'auth','signup':'auth','forgot':'forgot_password','reset':'reset_password',
    'verify':'verify_code','privacy':'privacy','terms':'terms','cookies':'cookies',
    'data-deletion':'data_deletion','contact':'contact',
    'guidelines':'community_guidelines','accessibility':'accessibility',
    '404':'404','400':'400','401':'401','403':'403','429':'429','500':'500',
    '503':'503','connection':'connection_error',
    'learning':'learning_hub','reader':'read_online','pdf-error':'pdf_unavailable',
    'recovery-sent':'password_recovery_sent','deletion-requested':'deletion_requested',
}


def page(name):
    if name not in PAGES:
        abort(404)
    if name in ('login','signup','forgot','reset','verify'):
        session.pop('user_id', None)
    else:
        session.update(user_id=1, user_name='reader_demo', user_display_name='Sample Reader')
    context = dict(values)
    context.update(username='reader_demo', email='reader@example.test', protected=False,
                   code_sent=True, deletion_return='settings', mode='signup' if name=='signup' else 'login',
                   token='preview-token', current_badge=None, unlocked_badges=[],
                   total_uploads=1, total_downloads=12,total_reviews=3,total_favorites=2, total_points=34, social_links={},
                   achievements=achievement_summary(12,2,3,8),streak=4,longest=8,
                   is_official=False, custom_badge=None,
                   user=(1,'reader_demo','reader@example.test',1,datetime(2026,10,1),None,'A sample reader bio.',{},'Sample','Reader',None),
                   profile=dict(username='reader_demo',first_name='Sample',last_name='Reader',bio='A sample reader bio.',social_links={},avatar_url=None),
                   pref=dict(notify_new_books=True,favorite_categories=[],email_frequency='weekly'),
                   notifications=[
                       dict(id=1,is_read=False,type='reply',actor_name='A sample member',created_at=datetime(2026,10,31,12),message='Thanks for sharing this book. The examples helped me understand the chapter.',link='/books'),
                       dict(id=2,is_read=False,type='approval',actor_name='DocoDive',created_at=datetime(2026,10,30,16),message='Your programming handbook has been approved and added to the library.',link='/books'),
                       dict(id=3,is_read=True,type='general_comment',actor_name='Another sample reader',created_at=datetime(2026,10,29,10),message='Is this a good place to start learning Python?',link='/books'),
                       dict(id=4,is_read=True,type='rejection',actor_name='DocoDive',created_at=datetime(2026,10,28,14),message='Please upload a clearer cover and check the title before submitting again.',link='/books'),
                   ])
    if name == 'learning':
        from learning_content import GENERIC_MODULES
        context.update(category_modules=GENERIC_MODULES,all_categories=[
            dict(slug='python',level='Python',count=3),
            dict(slug='javascript',level='JavaScript',count=2),
            dict(slug='data-science',level='Data Science',count=1),
        ])
    if name == 'stats':
        context.update(downloads=12,favorites=2,reviews=3,
                       unlocked_badges=[dict(key=b['key'],name=b['name'],icon='preview-'+b['key'],threshold=b['threshold']) for b in context['achievements']['items'] if b['unlocked']])
    if name == 'reader':
        context.update(book_title=sample_book['title'],book_id=4,pdf_url=url_for('book_pdf',book_id=4))
    if name == 'leaderboard':
        context.update(leaderboard=rank_leaders([
            dict(user_id=i,username='sample_reader_'+str(i),name=n,avatar_url=None,points=points,
                 weekly_change=change,badge_count=4,downloads=12,favorites=5,reviews=3,longest=8,is_official=False)
            for i,n,points,change in [(1,'Avery Sample',180,12),(2,'Jordan Sample',145,None),(3,'A reader with a very long display name',120,5),(4,'Casey Sample',100,0),(5,'Taylor Sample',100,2),(6,'Sam Sample',80,None)]
        ]),current_user_rank=1,current_user_points=180)
    if name == 'feedback':
        context['feedbacks']=[dict(id=i,subject=subject,message=message,created_at=datetime(2026,10,31,12),like_count=likes,
            official_reply=reply,official_replied_at=datetime(2026,10,31,14) if reply else None,username='sample_reader_'+str(i),avatar_url=None,user_id=i,is_liked=i==2)
            for i,subject,message,likes,reply in [
                (1,'Make it easier to continue a learning path','I would love a quick way to return to my current learning path from the library.',12,None),
                (2,'A clearer book preview on mobile','The preview should keep the title, author and actions together, including very long titles.',8,'Thanks for the detailed idea. We are reviewing the mobile preview experience.'),
                (3,'Support long discussions without squeezing text','This sample suggestion checks text wrapping, keyboard controls and a much longer discussion on a small screen.',3,None),
            ]]
    state=request.args.get('state')
    if state == 'expired' and name == 'login':
        flash('Login session expired. Please sign in again.', 'danger')
    if state == 'error' and name in ('login','signup'):
        context['error']='Please check your account details and try again. This is sample feedback only.'
    if state == 'empty':
        context.update(leaderboard=[],feedbacks=[],pdfs=[],trending_books=[],related_books=[],downloads=0,favorites=0,reviews=0,total_downloads=0,total_reviews=0,total_favorites=0,streak=0,longest=0,unlocked_badges=[],achievements=achievement_summary())
    if state in ('one','two') and name == 'leaderboard':
        context['leaderboard']=context['leaderboard'][:1 if state=='one' else 2]
    if state == 'visitor' and name == 'profile':
        context['user']=(2,'another_reader','private-address@example.test',1,datetime(2026,10,1),None,'A public profile with private account details hidden.',{},'Another','Reader',None)
    if state == 'official' and name == 'profile':
        context['is_official']=True
    if state == 'missing-activity' and name == 'profile':
        context.update(total_uploads=None,total_reviews=None,total_favorites=None,total_points=None,total_downloads=None,
                       achievements=None,profile_stats_unavailable=True)
    if name == 'preferences':
        context['categories']=['Python','Web Development','Software Architecture','Data Science','A much longer category title for small screens']
        if state == 'paused':
            context['pref']=dict(notify_new_books=False,favorite_categories=['Python','Data Science'],email_frequency='off')
    if name == 'reviews':
        context.update(avg_rating=4.7,total_reviews=3,breakdown={5:2,4:1,3:0,2:0,1:0},reviews=[
            dict(review_id=i,username='sample_reader_'+str(i),full_name=n,avatar=None,rating=rating,comment=comment,created_at='01 Nov 2026',
                 book_id=4 if i==1 else None,book_title=sample_book['title'] if i==1 else None,book_slug='synthetic-handbook' if i==1 else None)
            for i,n,rating,comment in [(1,'Avery Sample',5,'The learning paths helped me choose where to start. I found a useful programming book and saved it for later.'),(2,'Jordan Sample',4,'A good selection of resources. Clearer descriptions of the different editions would help.'),(3,'A sample reader with an exceptionally long display name',5,'I like having my favorites and downloads in one place. This is a synthetic review for layout testing only.')]
        ])
        if state == 'empty':
            context.update(avg_rating=0,total_reviews=0,breakdown={i:0 for i in range(1,6)},reviews=[])
        if state == 'no-books':
            context['books']=[]
    if state == 'guest':
        session.pop('user_id',None)
    if name == 'upload':
        context['categories']=['Python','Web Development','A longer category title for responsive testing']
        session['preview_upload_state']=state or 'ready'
    if name in ('400','401','403','429','500','503','connection'):
        context['trending_books']=[]
    context['user_logged_in']=bool(session.get('user_id'))
    return render_template('user/'+PAGES[name]+'.html', **context)


app.view_functions['home']=lambda:render_template('user/index.html',**dict(values,user_logged_in=bool(session.get('user_id'))))
app.add_url_rule('/preview/page/<name>', 'reader_preview_page', page)
@app.get('/preview/newsletter-welcome')
def preview_newsletter_welcome():
    from newsletter_presentation import build_newsletter_welcome
    return build_newsletter_welcome(
        'https://example.test/books', 'https://example.test/learn/python',
        'https://example.test/contact', 'https://example.test/privacy')['html']

@app.get('/preview/skeleton/<name>')
def preview_skeleton(name):
    if name not in PAGES and name not in ('lesson','practice'):
        abort(404)
    theme=request.args.get('theme','light')
    if theme not in ('light','dark'):
        abort(400)
    return render_template_string('''<!doctype html><html lang="en" data-bs-theme="{{ theme }}"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Skeleton composition preview · {{ name }}</title>
      <link rel="stylesheet" href="/static/css/tokens.css"><link rel="stylesheet" href="/static/css/loading.css">
      <style>#page-loader{animation:none!important}body{margin:0;background:var(--ui-bg)}</style></head><body>
      {% include 'shared/_page_skeleton.html' %}</body></html>''',
      name=name,theme=theme,skeleton_page=name,
      **({'skeleton_layout':name} if name in ('lesson','practice') else {}))
@app.get('/preview/lesson/<slug>/<module>')
def preview_lesson(slug,module):
    import re
    from types import SimpleNamespace
    from jinja2 import TemplateNotFound
    import learning_content
    from test_security_regressions import load_function
    if not re.fullmatch(r'[a-z0-9-]+',slug) or module not in ('beginner','intermediate','advanced','practice','reading','writing','speaking','listening'):
        abort(404)
    session.update(user_id=1,user_name='reader_demo',user_display_name='Sample Reader')
    def render(name,**context):return render_template(name,**dict(values,**context))
    scope=dict(vars(learning_content),mysql=SimpleNamespace(connection=SimpleNamespace(cursor=lambda:SimpleNamespace(close=lambda:None))),
               slug_to_category_name=lambda value,cur:value.replace('-',' ').title(),category_to_slug=lambda value:slug,
               abort=abort,render_template=render,TemplateNotFound=TemplateNotFound)
    if slug == 'python' and module == 'practice':
        return load_function('python_practice',scope)()
    return load_function('category_module',scope)(slug,module)
app.view_functions['python_practice']=lambda:preview_lesson('python','practice')
app.view_functions['category_module']=preview_lesson
for fixture_endpoint, fixture_name in {'all_books':'books','reviews_page':'reviews','user_feedback':'feedback','leaderboard':'leaderboard'}.items():
    app.view_functions[fixture_endpoint]=lambda fixture_name=fixture_name:page(fixture_name)
app.add_url_rule('/user/settings', 'account_settings', lambda: page('settings'))
app.add_url_rule('/user/account-deletion', 'account_deletion', lambda: page('deletion'))
app.view_functions['get_feedback_replies']=lambda feedback_id:jsonify([
    dict(id=100+feedback_id,user_id=2,username='sample_reader_2',avatar_url=None,is_liked=False,like_count=1,created_at='31 Oct 2026',message='A sample discussion reply. Thanks for sharing this idea.')])
app.view_functions['check_availability']=lambda:jsonify(exists=False,reserved=False,message='Available in this local preview.')
app.view_functions['get_comments']=lambda book_id,slug=None:jsonify([])
app.view_functions['get_notifications']=lambda:jsonify([
    dict(id=1,is_read=False,type='reply',actor_name='A sample member',created_at='2026-11-01T00:00:00Z',message='Thanks for sharing this book. The examples made the chapter much clearer.',link='/preview/page/detail'),
    dict(id=2,is_read=False,type='approval',actor_name='DocoDive',created_at='2026-10-31T12:00:00Z',book_title='Your programming handbook',message='Your book is approved and ready for the library.',link='/preview/page/detail'),
    dict(id=3,is_read=True,type='general_comment',actor_name='Another sample reader',created_at='2026-10-30T12:00:00Z',message='Is this a good place to start learning Python?',link='/preview/page/feedback')])
app.view_functions['unread_notification_count']=lambda:jsonify(count=2)

def preview_review_book_search():
    # Synthetic full-catalogue match beyond the initially rendered choices.
    catalogue=samples+[dict(id=250,title='Python beyond the first hundred',author='A sample catalogue author')]
    query=request.args.get('q','').strip().casefold()
    return jsonify(books=[dict(id=b['id'],title=b['title'],author=b.get('author','')) for b in catalogue
                          if query in b['title'].casefold() or query in b.get('author','').casefold()][:20],has_more=False)
app.view_functions['review_book_search']=preview_review_book_search
def preview_uploads():
    state=session.get('preview_upload_state')
    if state=='empty':return jsonify([])
    if state=='error':return jsonify(error='Sample upload history is unavailable.'),503
    if state=='unauthorized':return jsonify(error='Unauthorized'),401
    return jsonify([
        dict(id=4,title='A practical handbook for programming and reliable systems',author='A sample author',status='pending',created_at='2026-11-01 08:30:00'),
        dict(id=5,title='Short title',author='Another sample author',status='approved',created_at='2026-10-31 10:00:00'),
        dict(id=6,title='A very long book title that must remain readable without squeezing the status or icons on a small phone',author='A sample author with a longer name',status='rejected',created_at='2026-10-30 14:00:00'),
    ])
app.view_functions['user_uploads']=preview_uploads
app.view_functions['api_book_detail']=lambda book_id:jsonify(dict(
    next((book for book in samples if book['id']==book_id),sample_book),
    id=book_id,language='English',is_logged_in=bool(session.get('user_id')),is_favorite=False,
    reviews=[dict(username='sample_reader',rating=5,comment='A synthetic review for preview layout verification.')],
    description='A sample book preview. This fixture does not update views, downloads or any real record.'))

def fixture_pdf(book_id, slug=None, attachment=False):
    import fitz
    with fitz.open() as document:
        page=document.new_page()
        page.insert_text((60,80),'DocoDive synthetic PDF fixture',fontsize=18)
        page.insert_text((60,120),'Local sample only. No storage or database was contacted.')
        payload=document.tobytes()
    return send_file(BytesIO(payload),mimetype='application/pdf',as_attachment=attachment,
                     download_name='synthetic-book.pdf',conditional=True)
app.view_functions['book_pdf']=fixture_pdf
app.view_functions['download_book']=lambda book_id,slug=None:fixture_pdf(book_id,slug,attachment=True)

def fixture_book_qr(book_id, slug=None):
    import qrcode
    image=qrcode.make('https://example.test/book/fixture/'+str(book_id))
    payload=BytesIO();image.save(payload,format='PNG');payload.seek(0)
    return send_file(payload,mimetype='image/png')
app.view_functions['book_qr']=fixture_book_qr

# The isolated route builder keeps only the first decorator for each view.
# Include the numeric aliases used by the real reader and shared preview.
for rule, endpoint in (('/book/<int:book_id>/pdf','book_pdf'),
                       ('/book/<int:book_id>/download','download_book'),
                       ('/book/<int:book_id>/qr','book_qr')):
    if not any(str(existing)==rule for existing in app.url_map.iter_rules()):
        app.add_url_rule(rule,endpoint=endpoint,view_func=app.view_functions[endpoint])

# The practice endpoints are pure content filters. Run their real isolated bodies
# against the supplied lesson bank; never import the configured application.
from test_security_regressions import load_function
from learning_content import PYTHON_PRACTICE
from types import SimpleNamespace
practice_scope=dict(request=request,jsonify=jsonify,PYTHON_PRACTICE=PYTHON_PRACTICE,
                    random=SimpleNamespace(choice=lambda items:items[0]))
for endpoint in ('practice_challenges_api','practice_next_challenge'):
    app.view_functions[endpoint]=load_function(endpoint,practice_scope)

if __name__ == '__main__':
    print('Reader UI fixtures: http://127.0.0.1:5012/preview/page/settings | sample data only')
    app.run(host='127.0.0.1',port=5012,use_reloader=False,debug=False,load_dotenv=False)
