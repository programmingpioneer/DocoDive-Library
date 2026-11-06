"""Read-only checks of a running loopback app, including every published learning path."""
import argparse
import concurrent.futures
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.error import HTTPError


class LocalRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original, target = urlsplit(req.full_url), urlsplit(newurl)
        if (original.scheme, original.hostname, original.port) != (target.scheme, target.hostname, target.port):
            raise ValueError('Refusing to leave the local test app')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Hubs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        path = dict(attrs).get('href', '')
        if tag == 'a' and re.fullmatch(r'/learn/[a-z0-9-]+', path):
            self.paths.add(path)


def audit(base, output):
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.path not in ('', '/'):
        raise ValueError('Use only the local HTTP development app')

    def get(path):
        opener = build_opener(LocalRedirects())
        try:
            with opener.open(urljoin(base, path), timeout=40) as response:
                html = response.read().decode('utf-8', errors='replace')
                title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
                return dict(path=path, status=response.status, final_path=urlsplit(response.url).path,
                            title=re.sub(r'\s+', ' ', title[1]).strip() if title else '',
                            error='Traceback (most recent call last)' in html), html
        except HTTPError as error:
            return dict(path=path, status=error.code, error=True), ''
        except Exception as error:
            return dict(path=path, status=0, error=True, reason=type(error).__name__), ''

    first, html = get('/')
    parser = Hubs()
    parser.feed(html)
    paths = {'/books','/reviews','/feedback','/leaderboard','/privacy','/terms','/cookies',
             '/data-deletion','/contact','/community-guidelines','/accessibility',
             '/user/login','/user/signup','/forgot-password','/user/settings',
             '/user/favorites','/user/history','/user/stats','/user/preferences',
             '/user/profile/edit','/user/notifications','/user/upload','/user/account-deletion'}
    for hub in parser.paths:
        paths.add(hub)
        modules = ('listening','reading','writing','speaking') if hub.endswith('/ielts') else ('beginner','intermediate','advanced','practice')
        paths.update(hub+'/'+module for module in modules)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = [first] + [value[0] for value in executor.map(get, sorted(paths))]
    report = dict(base=base, total=len(results), hubs=len(parser.paths),
                  passed=sum(r['status']==200 and not r['error'] for r in results), results=results)
    Path(output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))
    for row in results:
        if row['status'] != 200 or row['error']:
            print(json.dumps(row))
    return 0 if report['passed']==report['total'] else 1


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--base', default='http://127.0.0.1:5001/')
    args.add_argument('--output', default='deliverables/reader-responsive/routes.json')
    options = args.parse_args()
    raise SystemExit(audit(options.base, options.output))
