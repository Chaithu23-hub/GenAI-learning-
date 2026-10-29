from types import SimpleNamespace


class FakeOpenAISDK:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello", tool_calls=[]))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
        )
