import pytest

from legal_rag.domain.policies import is_greeting


class TestGreetingDetection:
    @pytest.mark.parametrize("query", [
        "Hi", "hello", "Hey!", "hola", "Yo", "Howdy", "greetings",
        "Good morning", "Good afternoon", "Good evening", "good day",
        "how are you", "how's it going", "what's up",
        "thanks", "thank you", "thx", "ty",
        "bye", "goodbye", "see ya", "see you",
        "help", "what can you do?", "What can you help with",
    ])
    def test_bare_greeting_detected(self, query):
        assert is_greeting(query) is True

    @pytest.mark.parametrize("query", [
        "What is the late payment fee?",
        "hi, what does the amendment change?",         # greeting + real question
        "hello, when does the contract expire",
        "thanks, but I still need the termination clause",
        "help me draft a clause",
        "",                                              # empty
        "   ",                                           # whitespace
        "How does the amendment change the payment terms?",  # 'how' but not a greeting
    ])
    def test_real_question_not_greeting(self, query):
        assert is_greeting(query) is False

    def test_long_message_never_greeting(self):
        assert is_greeting("hello " + "x" * 50) is False
