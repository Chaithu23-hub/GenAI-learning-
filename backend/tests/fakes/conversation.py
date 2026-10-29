class FakeConversation:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def reply_if_general(self, query):
        self.calls.append(query)
        return self.reply
