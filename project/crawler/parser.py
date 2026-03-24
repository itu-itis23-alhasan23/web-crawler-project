from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse
from collections import Counter
import re


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    parsed = parsed._replace(fragment="")
    return urlunparse(parsed)


def normalize_word(word: str) -> str:
    """
    Better normalization for Turkish + general Unicode text.
    casefold() is stronger than lower().
    """
    return word.casefold()


def extract_words(text: str) -> list[str]:
    """
    Unicode-friendly token extraction.
    Keeps letters/digits from many languages, including Turkish.
    Excludes punctuation/underscore.
    """
    return [
        normalize_word(token)
        for token in re.findall(r"[^\W_]+", text, flags=re.UNICODE)
        if token.strip()
    ]


class SimpleHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links = []
        self.text_parts = []

        self.skip_tags = {"script", "style"}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in self.skip_tags:
            self.skip_depth += 1

        if tag == "a":
            href = None
            for key, value in attrs:
                if key.lower() == "href":
                    href = value
                    break

            if href:
                absolute = urljoin(self.base_url, href)
                absolute = normalize_url(absolute)

                if self._is_valid_http_url(absolute):
                    self.links.append(absolute)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def _is_valid_http_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_links_and_word_counts(html: str, base_url: str):
    parser = SimpleHTMLParser(base_url)
    parser.feed(html)

    full_text = " ".join(parser.text_parts)
    words = extract_words(full_text)
    word_counts = Counter(words)

    seen = set()
    unique_links = []
    for link in parser.links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    return unique_links, word_counts