"""Translate Markdown into the subset of HTML that Sublime can display."""

from html import escape
from html.entities import name2codepoint
from html.parser import HTMLParser
import os
import re
from urllib.parse import quote, unquote, urlsplit

from .._vendor.markdown import Markdown
from .._vendor.markdown.extensions.fenced_code import FencedCodeExtension
from .._vendor.markdown.extensions.tables import TableExtension
from .table import Cell, Table, text_width


STYLE = """
<style>
    .document { font-family: "Segoe UI", sans-serif;
                padding: 0.7rem 1.2rem 1.6rem 1.2rem; }
    p { margin: 0 0 0.8rem 0; }
    h1, h2, h3, h4, h5, h6 { margin: 0.9rem 0 0.5rem 0; }
    h1, h2 { border-bottom: 1px solid color(var(--foreground) alpha(0.22)); }
    .quote { margin: 0 0 0.8rem 0; padding-left: 0.8rem;
             border-left: 3px solid color(var(--foreground) alpha(0.35)); }
    code, .code { font-family: Consolas, monospace;
                  background-color: color(var(--foreground) alpha(0.09)); }
    .code { padding: 0.6rem; margin-bottom: 0.8rem; }
    .code code { background-color: transparent; }
    .list { margin: 0 0 0.7rem 1rem; }
    .item { margin-bottom: 0.2rem; }
    .rule { border-top: 1px solid color(var(--foreground) alpha(0.25));
            margin: 1rem 0; }
    .table { --table-border: color(var(--foreground) alpha(0.48));
             margin-bottom: 0.8rem; font-family: Consolas, monospace; }
    .table-slot { height: 0; }
    .table-cell, .table-header, .table-stripe {
        border-top: 1px solid var(--table-border);
        border-left: 1px solid var(--table-border);
        line-height: 1.35rem;
    }
    .table-content { padding-top: 0.18rem; }
    .table-header { font-weight: bold;
                    background-color: color(var(--accent) alpha(0.17)); }
    .table-stripe { background-color: color(var(--foreground) alpha(0.06)); }
    .table-bottom { height: 0; border-top: 1px solid var(--table-border);
                    border-right: 1px solid var(--table-border); }
    .link { color: var(--accent); text-decoration: underline; }
</style>
"""

FORMATTING_TAGS = {
    "code", "em", "h1", "h2", "h3", "h4", "h5", "h6", "p", "strong"
}
TASK_PREFIX = re.compile(r"^\[([ xX])\] +")
TEXT_WORDS = re.compile(r"\s+|\S+")


def local_path(filename, url):
    """Resolve a document-relative path without handing URLs to the OS."""
    if not filename or not url:
        return None
    try:
        parts = urlsplit(url)
        path = unquote(parts.path)
        if parts.scheme or parts.netloc or not path or os.path.isabs(path) or ":" in path:
            return None
        target = os.path.normpath(os.path.join(os.path.dirname(filename), path))
        if target.startswith(("\\\\", "//")) or not os.path.isfile(target):
            return None
        return target
    except (OSError, ValueError):
        return None


class MiniHtml(HTMLParser):
    def __init__(self, filename, table_width):
        super().__init__()
        self.filename = filename
        self.table_width = table_width
        self.output = []
        self.links = {}
        self.closers = []
        self.lists = []
        self.preformatted = False
        self.pending_marker = None
        self.table = None
        self.cell = None
        self.document_output = None
        # Minihtml's fallback CJK glyphs are wider than Sublime's measured Latin em.
        self.wrap_width = max(24, int(table_width * 0.85) - 4)
        self.text_line_width = 0
        self.pending_space = False

    def append_wrapped_text(self, text):
        for token in TEXT_WORDS.findall(text):
            if token.isspace():
                self.pending_space = self.text_line_width > 0
                continue
            width = text_width(token)
            if self.pending_space:
                if self.text_line_width + 1 + width > self.wrap_width:
                    self.output.append("<br>")
                    self.text_line_width = 0
                else:
                    self.output.append(" ")
                    self.text_line_width += 1
                self.pending_space = False
            if width <= self.wrap_width:
                if self.text_line_width + width > self.wrap_width:
                    self.output.append("<br>")
                    self.text_line_width = 0
                self.output.append(escape(token, quote=False))
                self.text_line_width += width
                continue
            for character in token:
                character_width = text_width(character)
                if self.text_line_width and self.text_line_width + character_width > self.wrap_width:
                    self.output.append("<br>")
                    self.text_line_width = 0
                self.output.append(escape(character, quote=False))
                self.text_line_width += character_width

    def emit_marker(self, text):
        if self.pending_marker is None:
            return text
        task = TASK_PREFIX.match(text)
        if task:
            self.output.append("☑ " if task.group(1).lower() == "x" else "☐ ")
            text = text[task.end():]
        else:
            self.output.append(self.pending_marker)
        self.pending_marker = None
        return text

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self.text_line_width = 0
            self.pending_space = False
        if tag == "li":
            marker = self.lists[-1]
            self.pending_marker = "• " if marker is None else "{}. ".format(marker)
            if marker is not None:
                self.lists[-1] += 1
        elif tag != "p" and self.pending_marker is not None:
            self.emit_marker("")

        if tag in FORMATTING_TAGS:
            self.output.append("<{}>".format(tag))
            close = "</{}>".format(tag)
        elif tag in ("ol", "ul"):
            self.lists.append(int(attrs.get("start", "1")) if tag == "ol" else None)
            self.output.append('<div class="list">')
            close = "</div>"
        elif tag == "li":
            self.output.append('<div class="item">')
            close = "</div>"
        elif tag == "pre":
            self.preformatted = True
            self.output.append('<div class="code">')
            close = "</div>"
        elif tag == "blockquote":
            self.output.append('<div class="quote">')
            close = "</div>"
        elif tag == "table":
            self.table = Table()
            close = ""
        elif tag == "tr":
            self.table.rows.append([])
            close = ""
        elif tag in ("td", "th"):
            self.cell = Cell(attrs.get("align"))
            self.document_output = self.output
            self.output = self.cell
            close = ""
        elif tag == "a":
            target = local_path(self.filename, attrs.get("href"))
            if target:
                token = "local-{}".format(len(self.links))
                self.links[token] = target
                self.output.append('<a href="{}">'.format(token))
                close = "</a>"
            else:
                self.output.append('<span class="link">')
                close = "</span>"
        elif tag == "img":
            alt = attrs.get("alt") or "Image"
            if self.cell:
                self.handle_data("[{}]".format(alt))
                return
            target = local_path(self.filename, attrs.get("src"))
            alt = escape(alt)
            if target and os.path.splitext(target)[1].lower() in (".png", ".jpg", ".jpeg", ".gif"):
                uri = "file:///" + quote(target.replace(os.sep, "/").lstrip("/"), safe="/:")
                self.output.append('<img src="{}" alt="{}">'.format(escape(uri), alt))
            else:
                self.output.append("<em>[{}]</em>".format(alt))
            return
        elif tag == "br":
            if self.cell:
                self.handle_data(" ")
            else:
                self.output.append("<br>")
            return
        elif tag == "hr":
            self.output.append('<div class="rule"></div>')
            return
        else:
            close = ""
        self.closers.append((tag, close))

    def handle_endtag(self, tag):
        if not self.closers or self.closers[-1][0] != tag:
            return
        if tag == "li" and self.pending_marker is not None:
            self.emit_marker("")
        if tag in ("ol", "ul"):
            self.lists.pop()
        if tag == "pre":
            self.preformatted = False
        self.output.append(self.closers.pop()[1])
        if tag in ("td", "th"):
            self.table.add_cell(self.cell)
            self.output = self.document_output
            self.document_output = None
            self.cell = None
        elif tag == "table":
            self.output.append(self.table.render(self.table_width))
            self.table = None

    def handle_data(self, text):
        if (not text.strip() and self.closers
                and self.closers[-1][0] in ("table", "thead", "tbody", "tr")):
            return
        if self.pending_marker is not None:
            if not text.strip():
                return
            text = self.emit_marker(text)
        if self.cell:
            self.cell.add_text(text.replace("\n", " "))
            return
        if self.preformatted:
            text = escape(text, quote=False)
            text = text.replace(" ", "&nbsp;").replace("\n", "<br>")
            self.output.append(text)
        else:
            self.append_wrapped_text(text)

    def handle_entityref(self, name):
        codepoint = name2codepoint.get(name)
        self.handle_data(chr(codepoint) if codepoint else "&{};".format(name))

    def handle_charref(self, name):
        try:
            codepoint = int(name[1:], 16) if name.lower().startswith("x") else int(name)
            character = chr(codepoint)
        except ValueError:
            character = "\ufffd"
        self.handle_data(character if not 0xd800 <= ord(character) <= 0xdfff else "\ufffd")


def render(text, filename, table_width=80):
    markdown = Markdown(
        extensions=[FencedCodeExtension(), TableExtension()],
        lazy_ol=False,
    )
    # Disable raw HTML while leaving entities and fenced code enabled.
    del markdown.preprocessors["html_block"]
    del markdown.inlinePatterns["html"]
    renderer = MiniHtml(filename, table_width)
    renderer.feed(markdown.convert(text))
    renderer.close()
    body = "".join(renderer.output) or "<p>Start typing to preview your Markdown.</p>"
    content = '<body id="markdown-preview-in-place">{}<div class="document">{}</div></body>'
    return content.format(STYLE, body), renderer.links
