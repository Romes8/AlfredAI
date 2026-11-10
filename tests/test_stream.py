from alfred.audio.stream import SentenceStreamer


def run(chunks):
    s = SentenceStreamer()
    out = []
    for c in chunks:
        out += s.feed(c)
    return out, s.flush()


def test_sentences_come_out_as_soon_as_they_end():
    s = SentenceStreamer()
    assert s.feed("Yo mate, the official site is ") == []
    assert s.feed("colosseo.it and tickets are about 18 euros. Book ") == [
        "Yo mate, the official site is colosseo.it and tickets are about 18 euros."]
    assert s.feed("ahead, it sells out!") == []  # no trailing space yet - could still be "..."
    assert s.flush() == ["Book ahead, it sells out!"]


def test_no_split_on_decimals_abbreviations_or_tiny_fragments():
    out, rest = run(["Lap was 1.23.4 so e.g. ", "faster than Dr. Who. ", "Yo. ", "That is the whole story. "])
    assert out == ["Lap was 1.23.4 so e.g. faster than Dr. Who.", "Yo. That is the whole story."]
    assert rest == []


def test_long_run_on_sentence_breaks_at_a_comma():
    text = "word " * 30 + ", and then " + "more " * 30
    out, rest = run([text])
    assert out and len(out[0]) <= 230 and rest
