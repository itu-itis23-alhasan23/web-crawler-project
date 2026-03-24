from crawler.parser import extract_links_and_word_counts


def test_parser():
    html = """
    <html>
      <head><title>Test Page</title></head>
      <body>
        <h1>Hello World</h1>
        <p>This is a test page. Hello again.</p>
        <a href="/about">About</a>
        <a href="https://example.org/contact">Contact</a>
        <script>var x = "should not be counted";</script>
      </body>
    </html>
    """

    links, counts = extract_links_and_word_counts(html, "https://example.com")

    print("Links:", links)
    print("Counts:", counts)

    assert "https://example.com/about" in links
    assert "https://example.org/contact" in links
    assert counts["hello"] == 2
    assert counts["world"] == 1
    assert "should" not in counts

    print("Parser test passed.")


if __name__ == "__main__":
    test_parser()
