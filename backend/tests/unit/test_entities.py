from legal_rag.domain.entities import Answer, Citation


class TestAnswer:
    def test_round_trip(self):
        answer = Answer(
            answer="a", reasoning="r",
            sources=(Citation(document="d.md", chunk_id="c", excerpt="e"),),
            confidence="high", out_of_scope=False,
        )
        payload = answer.to_dict()
        restored = Answer.from_dict(payload)
        assert restored == answer

    def test_from_dict_missing_sources_defaults_empty(self):
        payload = {"answer": "a", "reasoning": "r", "sources": [],
                   "confidence": "low", "out_of_scope": True}
        assert Answer.from_dict(payload).sources == ()
