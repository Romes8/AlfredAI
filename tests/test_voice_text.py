from alfred.agent.brain import wants_smart_model
from alfred.audio.confirm import parse_answer
from alfred.audio.tts import clean_for_speech, split_sentences
from alfred.audio.wake import find_wake

WORDS = ["alfred", "alfie", "al fred", "alfredo"]


def test_wake_with_command_in_one_breath():
    r = find_wake("Alfred, what's this on my screen?", WORDS)
    assert r and r.command == "what's this on my screen?"


def test_wake_hey_prefix_and_alias():
    assert find_wake("hey Alfie", WORDS).command == ""
    assert find_wake("Yo Alfred what's the weather", WORDS).command == "what's the weather"


def test_no_wake():
    assert find_wake("I was talking to Fred about dinner", WORDS) is None
    assert find_wake("", WORDS) is None


def test_confirm_parsing():
    assert parse_answer("Yeah do it") == "yes"
    assert parse_answer("nah") == "no"
    assert parse_answer("yes... no wait") == "no"  # no wins
    assert parse_answer("show me") == "show"
    assert parse_answer("banana") == "unclear"
    assert parse_answer("") == "unclear"


def test_speech_cleanup():
    assert clean_for_speech("**Sorted** - see [docs](https://x.y)") == "Sorted - see docs"
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_smart_model_trigger():
    t = ["think hard", "research"]
    assert wants_smart_model("Can you research GT3 setups", t)
    assert not wants_smart_model("what's this", t)
