"""Pure multipart welcome content; sending and subscription state live elsewhere."""

from datetime import datetime, timezone
from html import escape
from ipaddress import ip_address
import re
from urllib.parse import urlsplit


DEFAULT_NEWSLETTER_SITE = "https://docodive-library.onrender.com"


def newsletter_site_base(configured=None):
    """Return a configured origin, never an incoming request's Host header."""
    base = configured or DEFAULT_NEWSLETTER_SITE
    if not isinstance(base, str) or any(character.isspace() or ord(character) < 32
                                        for character in base) or "\\" in base:
        raise ValueError("Invalid newsletter site origin")
    parsed = urlsplit(base)
    host = parsed.hostname
    # Accessing .port also rejects malformed and out-of-range port numbers.
    port = parsed.port
    if (not host or port == 0 or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Newsletter site must be an origin without credentials or extra URL parts")
    local = host in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Newsletter site requires HTTPS; explicit loopback HTTP is allowed")
    try:
        address = ip_address(host)
    except ValueError:
        if not local and ("." not in host or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in host.split("."))):
            raise ValueError("Invalid public newsletter hostname")
    else:
        if not local and not address.is_global:
            raise ValueError("Newsletter site must be public or explicit loopback")
    return parsed.scheme + "://" + parsed.netloc.rstrip("/")


def build_newsletter_welcome(library_url, learning_url, contact_url, privacy_url, support_email=None):
    """Build a table-based welcome with absolute, HTML-escaped application links."""
    links = (library_url, learning_url, contact_url, privacy_url)
    for url in links:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("https", "http") or not parsed.netloc
                or any(ord(character) < 32 for character in url)):
            raise ValueError("Welcome email links must be absolute HTTP(S) URLs")
    library, learning, contact, privacy = (escape(url, quote=True) for url in links)
    support = ""
    if support_email and re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", support_email):
        support = (f' Or <a href="mailto:{escape(support_email, quote=True)}" '
                   'style="color:#4F46E5;text-decoration:underline;">email our team</a>.')
    year = datetime.now(timezone.utc).year
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting"><title>Welcome to DocoDive</title>
<style>@media only screen and (max-width:620px){{.email-pad{{padding:28px 24px!important}}.email-title{{font-size:34px!important;line-height:39px!important}}.email-shell{{border-radius:0!important}}}}</style>
</head><body style="margin:0;padding:0;background:#EEF2FF;color:#25324B;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Welcome to the DocoDive newsletter. Find your next great read.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#EEF2FF;">
<tr><td align="center" style="padding:32px 12px;">
<table role="presentation" class="email-shell" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;border-radius:24px;background:#FFFFFF;overflow:hidden;">
  <tr><td class="email-pad" bgcolor="#17223D" style="padding:28px 40px;background:#17223D;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td width="42" height="42" align="center" bgcolor="#6366F1" style="width:42px;height:42px;background:#6366F1;border-radius:12px;color:#FFFFFF;font-size:25px;font-weight:bold;">D<span style="color:#A5F3FC;">.</span></td>
      <td style="padding-left:13px;color:#FFFFFF;"><strong style="font-size:21px;line-height:26px;">DocoDive</strong><br><span style="font-size:12px;line-height:19px;color:#C7D2FE;">A home for curious minds.</span></td>
    </tr></table>
  </td></tr>
  <tr><td class="email-pad" style="padding:42px 40px 34px;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td bgcolor="#CCFBF1" style="padding:7px 11px;background:#CCFBF1;border-radius:6px;color:#115E59;font-size:11px;line-height:16px;font-weight:bold;letter-spacing:1.1px;">WELCOME TO THE NEWSLETTER</td></tr></table>
    <h1 class="email-title" style="margin:22px 0 18px;color:#17223D;font-size:42px;line-height:47px;letter-spacing:-1px;font-weight:800;">Good books.<br><span style="color:#4F46E5;">Fresh perspectives.</span></h1>
    <p style="margin:0 0 14px;color:#334155;font-size:16px;line-height:26px;">Thanks for joining the DocoDive newsletter. We're glad you're here.</p>
    <p style="margin:0;color:#64748B;font-size:15px;line-height:25px;">There is always something new to learn. Start with a book that sparks your curiosity, then see where it takes you.</p>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:26px 0 0;"><tr><td bgcolor="#4F46E5" style="background:#4F46E5;border-radius:10px;">
      <a href="{library}" style="display:inline-block;padding:16px 23px;color:#FFFFFF;font-size:15px;line-height:20px;font-weight:bold;text-decoration:none;border-radius:10px;">Browse the library &rarr;</a>
    </td></tr></table>
  </td></tr>
  <tr><td class="email-pad" style="padding:0 40px 36px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #E2E8F0;border-radius:14px;">
      <tr><td style="padding:22px 22px 16px;color:#17223D;font-size:12px;line-height:18px;font-weight:bold;letter-spacing:1px;">MAKE YOURSELF AT HOME</td></tr>
      <tr><td style="padding:0 22px 20px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          <td width="36" valign="top" style="width:36px;color:#4F46E5;font-size:17px;line-height:25px;font-weight:bold;">01</td>
          <td><a href="{library}" style="color:#17223D;font-size:15px;line-height:23px;font-weight:bold;text-decoration:none;">Find a book worth your time</a><p style="margin:5px 0 0;color:#64748B;font-size:13px;line-height:21px;">Explore the free library and follow the subjects that interest you.</p></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:0 22px 22px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          <td width="36" valign="top" style="width:36px;color:#0F766E;font-size:17px;line-height:25px;font-weight:bold;">02</td>
          <td><a href="{learning}" style="color:#17223D;font-size:15px;line-height:23px;font-weight:bold;text-decoration:none;">Build a little momentum</a><p style="margin:5px 0 0;color:#64748B;font-size:13px;line-height:21px;">Visit the Python Learning Hub for a focused place to begin.</p></td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>
  <tr><td class="email-pad" bgcolor="#FEF3C7" style="padding:23px 40px;background:#FEF3C7;">
    <p style="margin:0;color:#78350F;font-size:14px;line-height:23px;"><strong>A small thought to take with you</strong><br>You do not have to learn everything today. One good page is a good start.</p>
  </td></tr>
  <tr><td class="email-pad" style="padding:28px 40px;background:#F8FAFC;">
    <p style="margin:0 0 12px;color:#475569;font-size:12px;line-height:20px;">You received this welcome because you subscribed to the DocoDive newsletter.</p>
    <p style="margin:0 0 17px;color:#64748B;font-size:12px;line-height:20px;">Need help with your subscription? <a href="{contact}" style="color:#4F46E5;text-decoration:underline;">Contact us</a>.{support}</p>
    <p style="margin:0;color:#64748B;font-size:11px;line-height:19px;">&copy; {year} DocoDive <span style="color:#CBD5E1;">&nbsp;|&nbsp;</span> <a href="{privacy}" style="color:#64748B;text-decoration:underline;">Privacy</a></p>
  </td></tr>
</table>
</td></tr></table></body></html>"""
    text = "\n".join([
        "Welcome to DocoDive",
        "",
        "Thanks for joining the DocoDive newsletter. We're glad you're here.",
        "Start with a book that sparks your curiosity, then see where it takes you.",
        "",
        "Browse the free library: " + library_url,
        "Explore the Python Learning Hub: " + learning_url,
        "",
        "You do not have to learn everything today. One good page is a good start.",
        "",
        "You received this welcome because you subscribed to the DocoDive newsletter.",
        "Need help with your subscription? Contact us: " + contact_url,
        "Privacy: " + privacy_url,
    ])
    return {"subject": "Welcome to DocoDive", "text": text, "html": html}
