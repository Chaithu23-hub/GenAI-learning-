class FakeConversation:
    def __init__(self, reply=None, route="documents"):
        self.response = reply
        self.route = route
        self.classifications = []
        self.replies = []

    def classify(self, query):
        self.classifications.append(query)
        return self.route

    def reply(self, query):
        self.replies.append(query)
        return self.response


class FakeUnsupportedResponses:
    def __init__(self, reply="Please provide supporting document evidence."):
        self.answer = reply
        self.calls = []

    def reply(self, reason):
        self.calls.append(reason)
        return self.answer
