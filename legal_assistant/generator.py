import json
import urllib.request

from . import config
from .retrieval import retrieve
from .schema import parse_json_response, validate_response

SYSTEM_PROMPT = """ROLE
You are a precise, citation-first legal assistant for a law firm's internal knowledge base.

TASK
Answer the user's question using ONLY the retrieved document chunks. You never guess or invent.

CONTEXT
The retrieved chunks for the current question arrive in the user message as a JSON list with
fields chunk_id, document, heading, excerpt. They are the only facts you may rely on.

CONSTRAINTS
1. Every claim must trace back to a retrieved chunk; cite document and chunk_id in "sources", with a supporting "excerpt" copied verbatim from the chunk.
2. If multiple chunks are relevant, synthesise them but cite each one.
3. If retrieved chunks contradict each other (e.g. an amendment changes a contract clause), surface BOTH versions and note the conflict explicitly.
4. If the answer is not in the retrieved chunks, set out_of_scope to true and set answer exactly to: "I don't know \u2014 this information is not in the provided documents."
5. Never draft, modify, or invent contract language; retrieve and explain only.

EXAMPLES
Question: What is the late payment interest rate under the Master Services Agreement?
{"answer": "The original MSA sets late-payment interest at 1.0% per month, but Amendment No. 1 deleted and replaced Section 3 and raised it to 1.5% per month. Both versions are surfaced; the amendment controls.", "reasoning": "Two retrieved chunks state the rate: master_services_agreement.md Section 3 says 1.0% per month, while amendment_01_payment_terms.md replaces Section 3 with 1.5% per month. Because they conflict, both are reported and the amendment's controlling language is noted.", "sources": [{"document": "master_services_agreement.md", "chunk_id": "master_services_agreement::003", "excerpt": "Late payments shall accrue interest at a rate of 1.0% per month, or the maximum rate permitted by law, whichever is lower."}, {"document": "amendment_01_payment_terms.md", "chunk_id": "amendment_01_payment_terms::002", "excerpt": "Late payments shall accrue interest at a rate of 1.5% per month, or the maximum rate permitted by law, whichever is lower."}], "confidence": "high", "out_of_scope": false}

Question: What is the capital of France?
{"answer": "I don't know \u2014 this information is not in the provided documents.", "reasoning": "No retrieved chunk mentions France or its capital, so the question lies outside the knowledge base and must be refused.", "sources": [], "confidence": "low", "out_of_scope": true}

OUTPUT FORMAT
Respond with a single JSON object and nothing else:
{
  "answer": "your grounded answer",
  "reasoning": "step-by-step explanation of how the retrieved chunks lead to the answer",
  "sources": [{"document": "filename", "chunk_id": "id", "excerpt": "exact supporting passage"}],
  "confidence": "high | medium | low",
  "out_of_scope": false
}

TONE
Formal, neutral, concise. Quote contract language verbatim where precision matters."""

# the Python function below performs the actual search — the model never does.
RETRIEVE_TOOL = {
    "type": "function",
    "function": {
        "name": "retrieve_chunks",
        "description": "Search the firm's legal document knowledge base for passages relevant to a question.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "document_type": {
                    "type": "string",
                    "enum": ["contract", "amendment"],
                    "description": "Optional: restrict the search to contracts or amendments.",
                },
            },
            "required": ["query"],
        },
    },
}

_EXCERPT_CHARS = 400


def _log_usage(response):
    # the bill; logging them per call lets cost per request be tracked.
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    import sys

    print(
        f"[token usage] prompt={getattr(usage, 'prompt_tokens', '?')} "
        f"completion={getattr(usage, 'completion_tokens', '?')} "
        f"total={getattr(usage, 'total_tokens', '?')}",
        file=sys.stderr,
    )


_CONCEPT_REQUIREMENTS = {
    # Legal concept -> list of required phrases/concepts that must appear
    "takings clause": ["public", "compensation"],  # Must mention both "public use" and "compensation"
    "bill of rights": ["liberties", "government"],  # Context on what they protect
    "amendments": ["amendment", "ratified"],  # Must reference actual amendments
    "sovereignty": ["states", "immunity"],  # Sovereign immunity context
    "double jeopardy": ["twice", "same crime"],  # Clear on the "twice" concept
    "jury trial": ["criminal", "civil"],  # When applicable (if comparing)
    "amendment gaps": ["year", "decades"],  # Should mention timeframes
    "anti-federalist": ["feared", "government", "liberty"],  # Context on their concerns
}


def _check_answer_completeness(question: str, answer_dict: dict) -> dict:
    question_lower = question.lower()
    answer_lower = answer_dict.get("answer", "").lower()
    
    # Identify which concept is being asked about
    relevant_concept = None
    for concept in _CONCEPT_REQUIREMENTS.keys():
        if concept in question_lower:
            relevant_concept = concept
            break
    
    if not relevant_concept:
        # No special requirements, answer is fine
        return {
            "complete": True,
            "missing_concepts": [],
            "suggested_confidence": answer_dict.get("confidence", "medium"),
        }
    
    # Check if all required elements are present
    required_terms = _CONCEPT_REQUIREMENTS[relevant_concept]
    missing = [term for term in required_terms if term not in answer_lower]
    
    if not missing:
        # All requirements met
        return {
            "complete": True,
            "missing_concepts": [],
            "suggested_confidence": answer_dict.get("confidence", "medium"),
        }
    else:
        # Missing key concepts — downgrade confidence
        current_confidence = answer_dict.get("confidence", "medium")
        
        # Downgrade: high→medium, medium→low, low→low
        suggested = "low" if current_confidence in ["high", "medium"] else "low"
        
        return {
            "complete": False,
            "missing_concepts": missing,
            "suggested_confidence": suggested,
        }


def _apply_completeness_adjustment(payload: dict, question: str) -> dict:
    if payload.get("out_of_scope"):
        # Out-of-scope already handled correctly
        return payload
    
    completeness = _check_answer_completeness(question, payload)
    
    if not completeness["complete"]:
        # Downgrade confidence to reflect incompleteness
        payload["confidence"] = completeness["suggested_confidence"]
        payload["reasoning"] = (
            payload.get("reasoning", "")
            + f" [Confidence downgraded to '{completeness['suggested_confidence']}' "
            f"due to missing legal elements: {', '.join(completeness['missing_concepts'])}]"
        )
    
    return payload


def detect_llm_model():

    url = config.LLM_BASE_URL.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            if not (200 <= resp.status < 300):
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    names = [m.get("id") for m in data.get("data", []) if m.get("id")]
    if config.LLM_MODEL in names:
        return config.LLM_MODEL
    if names:
        import sys

        print(
            f"Note: configured model '{config.LLM_MODEL}' not found on the server; "
            f"using '{names[0]}' instead.",
            file=sys.stderr,
        )
        return names[0]
    return None


def _chunks_payload(chunks):
    return [
        {
            "chunk_id": c.chunk_id,
            "document": c.document,
            "heading": c.heading,
            "excerpt": c.text[:600],
        }
        for c in chunks
    ]


def _out_of_scope():
    return {
        "answer": config.OUT_OF_SCOPE_ANSWER,
        "reasoning": (
            "No retrieved chunk scored above the relevance threshold, so the "
            "knowledge base contains no grounded answer for this question."
        ),
        "sources": [],
        "confidence": "low",
        "out_of_scope": True,
    }


class ExtractiveGenerator:

    def generate(self, query, where=None):
        chunks = retrieve(query, where=where)
        relevant = [c for c in chunks if c.score >= config.MIN_RELEVANT_SCORE]
        if not relevant:
            return _out_of_scope()

        confidence = "high" if relevant[0].score >= config.HIGH_CONFIDENCE_SCORE else "medium"

        # retrieved chunk verbatim, so every sentence maps to a source below.
        parts, sources = [], []
        for c in relevant:
            location = f'{c.document}, section "{c.heading}"' if c.heading != "Preamble" else c.document
            parts.append(f'According to {location}: "{c.text[:_EXCERPT_CHARS]}"')
            sources.append({
                "document": c.document,
                "chunk_id": c.chunk_id,
                "excerpt": c.text[:_EXCERPT_CHARS],
            })

        payload = {
            "answer": "Based on the retrieved documents: " + " ".join(parts),
            "reasoning": (
                f"Retrieved {len(relevant)} relevant chunk(s); top cross-encoder "
                f"score {relevant[0].score:.2f}. The answer quotes each chunk "
                "verbatim, so every claim maps directly to a source below."
            ),
            "sources": sources,
            "confidence": confidence,
            "out_of_scope": False,
        }
        
        # FIX FOR PROBLEM 1: Apply completeness check to avoid shallow answers
        payload = _apply_completeness_adjustment(payload, query)
        
        return payload


def _verify_sources(payload):
    # only accepted if their citations can be resolved to real stored chunks.
    from .vector_store import get_collection

    collection = get_collection()
    errors = []
    for source in payload["sources"]:
        chunk_id = source["chunk_id"]
        try:
            result = collection.get(ids=[chunk_id], include=["documents"])
        except Exception:
            errors.append(f"could not look up chunk_id {chunk_id}")
            continue
        if not result["ids"]:
            errors.append(f"cited chunk_id {chunk_id} does not exist in the knowledge base")
            continue
        stored_text = (result["documents"][0] or "")
        excerpt = source["excerpt"].strip()
        if excerpt and excerpt not in stored_text:
            errors.append(f"excerpt for {chunk_id} does not match the stored chunk text")
    return errors


class LLMGenerator:

    MAX_TOOL_ROUNDS = 4

    def __init__(self, model=None):
        from openai import OpenAI

        self.client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
        self.model = model or config.LLM_MODEL

    def generate(self, query, where=None):
        try:
            return self._generate_llm(query, where=where)
        except Exception as exc:
            import sys

            print(f"Warning: LLM backend failed ({exc}); falling back to extractive.",
                  file=sys.stderr)
            return ExtractiveGenerator().generate(query, where=where)

    def _generate_llm(self, query, where=None):
        initial_hits = retrieve(query, where=where)
        context = json.dumps(_chunks_payload(initial_hits), indent=2)
        user_content = (
            f"{query}\n\n"
            f"Retrieved document chunks (cite ONLY these chunk_ids in sources):\n{context}\n\n"
            f"Answer using only these chunks. You may call retrieve_chunks for more."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        message = None
        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[RETRIEVE_TOOL],
                temperature=config.LLM_TEMPERATURE,
            )
            _log_usage(response)
            message = response.choices[0].message
            if not message.tool_calls:
                break
            messages.append(message)
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                tool_where = (
                    {"document_type": args["document_type"]}
                    if args.get("document_type")
                    else where
                )
                hits = retrieve(args.get("query", query), where=tool_where)
                # search to contracts or amendments via the tool argument.
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(_chunks_payload(hits)),
                })
        else:
            # Ran out of tool rounds without a final answer.
            return ExtractiveGenerator().generate(query, where=where)

        # AND verify its citations resolve to real stored chunks; if either
        # fails, retry exactly once with a correction prompt.
        for attempt in range(2):
            errors = None
            try:
                payload = parse_json_response(message.content or "")
                errors = validate_response(payload) + _verify_sources(payload)
                if not errors:
                    # FIX FOR PROBLEM 1: Apply completeness check to avoid shallow answers
                    payload = _apply_completeness_adjustment(payload, query)
                    return payload
            except (ValueError, json.JSONDecodeError) as exc:
                errors = [f"response did not contain a JSON object ({exc})"]
            if attempt == 0:
                messages.append(message)
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous reply did not match the required JSON schema: "
                        + "; ".join(errors)
                        + "\nReply again with ONLY the corrected JSON object."
                    ),
                })
                retry = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=config.LLM_TEMPERATURE,
                )
                _log_usage(retry)
                message = retry.choices[0].message
        import sys

        print("Warning: LLM answer failed validation twice; using extractive fallback.",
              file=sys.stderr)
        return ExtractiveGenerator().generate(query, where=where)


def get_generator(backend=None):
    if backend == "auto":
        backend = None
    if backend == "extractive":
        return ExtractiveGenerator()
    if backend == "llm":
        return LLMGenerator(model=detect_llm_model())
    detected = detect_llm_model()
    if detected:
        return LLMGenerator(model=detected)
    return ExtractiveGenerator()
