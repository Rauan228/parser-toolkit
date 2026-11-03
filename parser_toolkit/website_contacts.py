"""Small, bounded crawl of a company's public HTML contact pages."""
from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Tuple
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from parser_toolkit.core.contacts import link_type, make_contact, unique_contacts
from parser_toolkit.core.http import HttpClient

EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.U)
PHONE_RE = re.compile(r"(?<!\w)(?:\+7|8)(?:[\s().\-–‒]*\d){10}(?:\s*[,;]?\s*доб\.?\s*\d+)?(?!\d)")
CONTACT_PAGE_RE = re.compile(r"контакт|связаться|contact|requisites|реквизит|about|о компании", re.I)
BLOCKS = {"p", "div", "li", "td", "section", "article", "address", "header", "footer"}
SKIP = {"script", "style", "noscript", "template", "svg"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class Node:
    def __init__(self, tag="", attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children: List[Any] = []

    def text(self):
        return " ".join(c.text() if isinstance(c, Node) else c for c in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        node = self.current
        while node.parent:
            if node.tag in SKIP or "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true":
                return
            node = node.parent
        self.current.children.append(data)


def _label(node: Node, value: str) -> str:
    """Use a small local text block; never infer a person's role from a domain."""
    current = node
    for _ in range(4):
        if current.tag in BLOCKS or current is node:
            text = " ".join(current.text().split())
            stripped = text.replace(value, "").strip(" :;,-–|")
            if (stripped and len(text) <= 200 and len(EMAIL_RE.findall(text)) <= 1
                    and len(PHONE_RE.findall(text)) <= 1):
                # A phone rendered with spaces is still just a phone, not a label.
                if not PHONE_RE.fullmatch(text) and not EMAIL_RE.fullmatch(text):
                    if text.lower() not in ("позвонить", "написать", "whatsapp", "telegram", "e-mail", "email"):
                        return text
        if current.parent is None:
            break
        current = current.parent
    return ""


def extract_contacts(html: str, source_url: str) -> Tuple[List[Dict[str, str]], List[str]]:
    doc = Document()
    doc.feed(html)
    result, links = [], []
    nodes = list(doc.root.walk())
    for node in nodes:
        # Skip script content and anchors inside hidden blocks.
        ancestor = node
        hidden = False
        while ancestor.parent:
            if ancestor.tag in SKIP or "hidden" in ancestor.attrs or ancestor.attrs.get("aria-hidden") == "true":
                hidden = True
                break
            ancestor = ancestor.parent
        if hidden:
            continue
        href = node.attrs.get("href") or ""
        if node.tag == "a" and href:
            absolute = urljoin(source_url, href)
            low = href.lower()
            kind = ""
            if low.startswith("mailto:"):
                kind, absolute = "email", unquote(href[7:].split("?", 1)[0])
            elif low.startswith("tel:"):
                kind, absolute = "phone", unquote(href[4:])
            elif link_type(absolute) in ("whatsapp", "telegram", "viber"):
                kind = link_type(absolute)
            if kind:
                values = EMAIL_RE.findall(absolute) if kind == "email" else [absolute]
                for value in values:
                    result.append(make_contact(kind, value, label=_label(node, value), source_url=source_url))
            elif CONTACT_PAGE_RE.search(unquote(href) + " " + node.text()):
                links.append(absolute)
        # A tel/mailto anchor already has the canonical value (and possibly an
        # extension). Do not rediscover its formatted visible text as a second contact.
        ancestor = node
        inside_contact_anchor = False
        while ancestor.parent:
            if ancestor.tag == "a" and str(ancestor.attrs.get("href", "")).lower().startswith(("tel:", "mailto:")):
                inside_contact_anchor = True
                break
            ancestor = ancestor.parent
        if inside_contact_anchor:
            continue
        # Read only direct visible text, avoiding duplicate whole-page scans.
        for text in node.children:
            if not isinstance(text, str):
                continue
            for kind, regex in (("email", EMAIL_RE), ("phone", PHONE_RE)):
                for match in regex.finditer(text):
                    result.append(make_contact(kind, match.group(), label=_label(node, match.group()), source_url=source_url))
    contacts = unique_contacts(result)
    # Prefer a labeled occurrence when the same value has an unlabeled duplicate.
    labeled = {(c["type"], c["value"], c["source_url"], c["extension"]) for c in contacts if c["label"]}
    contacts = [c for c in contacts if c["label"] or
                (c["type"], c["value"], c["source_url"], c["extension"]) not in labeled]
    return contacts, list(dict.fromkeys(links))


def _host(url):
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def crawl_website(url: str, *, max_pages: int = 3, timeout: float = 15, sleep: float = 0.7,
                  proxy: str = "") -> Tuple[List[Dict[str, str]], List[str]]:
    """Homepage + contact/about links on the same host. Failures stay visible."""
    if not urlsplit(url).scheme:
        url = "https://" + url
    if urlsplit(url).scheme not in ("http", "https") or not _host(url) or link_type(url) != "website":
        return [], []
    client = HttpClient(timeout=timeout, retries=1, proxy=proxy)
    pending, seen, result, errors = [url], set(), [], []
    while pending and len(seen) < max_pages:
        page = pending.pop(0)
        p = urlsplit(page)
        page = urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))
        if page in seen or _host(page) != _host(url) or p.scheme not in ("http", "https"):
            continue
        seen.add(page)
        if len(seen) > 1:
            time.sleep(sleep)
        try:
            html = client.get(page, accept="text/html,application/xhtml+xml")
            if "<html" not in html[:5000].lower() and "<a " not in html.lower():
                errors.append(f"{page}: страница не содержит доступный HTML")
                continue
            contacts, links = extract_contacts(html, page)
            result.extend(contacts)
            pending.extend(link for link in links if link not in seen and _host(link) == _host(url))
        except Exception as exc:
            errors.append(f"{page}: {exc}")
    return unique_contacts(result), errors
