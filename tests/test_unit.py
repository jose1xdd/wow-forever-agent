import pytest

from wow_knowledge.ingestion import check_public_host, classify, extract_html, normalize_url, split_chunks


def test_rejects_local_and_unsafe_urls():
    for url in ("http://example.com", "file:///etc/passwd",
                "https://a.example.com:8080/", "https://user:pass@example.com/"):
        with pytest.raises(ValueError):
            normalize_url(url)
    with pytest.raises(ValueError):
        check_public_host("127.0.0.1")


def test_html_extract_avoids_navigation_and_scripts():
    doc = extract_html(b'<html lang="en"><head><title>Legacy</title></head><body><nav>noise</nav><article><h1>Legacy Points</h1><p>World of Warcraft Forever has a Legacy System for every character and you can choose different perks for each one.</p><script>bad()</script></article></body></html>')
    assert "Legacy Points" in doc["body"]
    assert "bad()" not in doc["body"]
    assert "noise" not in doc["body"]


def test_utf8_characters_are_preserved():
    raw = ("<main><h1>WoW Forever</h1><p>Un jugador preguntó cómo ganar puntos de Legacy "
           "y respondió: ¡Sí, aún se puede! Esta es una guía extensa para aventureros.</p></main>").encode()
    assert "preguntó cómo" in extract_html(raw)["body"]


def test_ambiguous_builds_never_auto_joined():
    assert classify("Hunter leveling", "1.60.1.70707 and 1.60.1.70862")["build"] is None
    assert classify("Hunter leveling", "1.60.1.70862")["class_name"] == "Hunter"


def test_chunks_are_bounded():
    chunks = split_chunks("some words in a longer guide " * 100, size=300)
    assert len(chunks) > 1
    assert all(len(chunk) <= 320 for chunk in chunks)
