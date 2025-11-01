import re
import html
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_url_re = re.compile(r'^(https?://)', re.IGNORECASE)


def _link_sub(match):
    text = match.group(1)
    url = match.group(2).strip()
    # Only allow http/https links
    if not _url_re.match(url):
        # If invalid URL, render the literal source safely
        return html.escape(f'[{text}]({url})')
    return (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">'
        f'{html.escape(text)}</a>'
    )


@register.filter(name='format_ach')
def format_ach(value):
    """
    Minimal, safe formatter for achievements:
    - Bold: **text** -> <strong>text</strong>
    - Link: [text](https://example.com) -> <a href="...">text</a>
    - Preserves newlines as <br>
    Everything else is escaped to prevent HTML injection.
    """
    if value is None:
        return ''
    # Escape entire string first
    s = html.escape(str(value))
    # Bold
    s = re.sub(r'\*{2}(.+?)\*{2}', r'<strong>\1</strong>', s)
    # Links
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link_sub, s)
    # Newlines
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')
    return mark_safe(s)


@register.filter(name='format_desc')
def format_desc(value):
    """
    Safe formatter for description blocks supporting:
    - Bold: **text**
    - Links: [text](https://example.com)
    - Bullet lists: lines starting with '-', '*', or '•'
    - Normal lines rendered as paragraphs
    All content is HTML-escaped before inline formatting is applied.
    """
    if value is None:
        return ''
    # Normalize and escape
    raw = str(value).replace('\r\n', '\n').replace('\r', '\n')
    lines = raw.split('\n')

    def _inline_format(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r'\*{2}(.+?)\*{2}', r'<strong>\1</strong>', s)
        s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link_sub, s)
        return s

    out = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        # Blank line ends a list and separates paragraphs
        if stripped == '':
            if in_list:
                out.append('</ul>')
                in_list = False
            # Do not emit empty <p>; just skip
            continue
        # Bullet detection
        if stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('• '):
            if not in_list:
                out.append('<ul>')
                in_list = True
            # Remove bullet prefix
            content = stripped[2:] if stripped[1] == ' ' else stripped[2:]
            out.append(f'<li>{_inline_format(content)}</li>')
            continue
        # Normal text line
        if in_list:
            out.append('</ul>')
            in_list = False
        out.append(f'<p>{_inline_format(stripped)}</p>')
    if in_list:
        out.append('</ul>')
    return mark_safe('\n'.join(out))