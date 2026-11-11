import re
import uuid
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import ValidationError

from ..config import settings
from ..db import connection, now
from ..knowledge import retrieve
from .. import tools as domain

PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text(encoding="utf-8")


def customer_answer(text: str) -> str:
    """Keep provenance internal while preserving factual uncertainty."""
    text = re.sub(r"\[[^\]]*\.pdf[^\]]*\]|\([^)]*\.pdf[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"Assignment\s*[-–—]\s*AI Voice Bot Development\.pdf(?:,?\s*pages?\s*[\d–-]+)?", "", text, flags=re.I)
    text = re.sub(r"\bassignment[- ]provided indications\b", "indicative figures", text, flags=re.I)
    text = re.sub(r"\bassignment[- ]provided\b", "indicative", text, flags=re.I)
    text = re.sub(r"\bfigures are indicative figures\b", "figures are indicative", text, flags=re.I)
    text = re.sub(r"\b(?:the|our) assignment(?: documents?)?\b", "the available information", text, flags=re.I)
    text = re.sub(r"\bavailable documentation\b", "available information", text, flags=re.I)
    text = re.sub(r"\b(?:according to|as stated in|as noted in) the available information\b", "", text, flags=re.I)
    text = re.sub(r"^(?:the )?available information (?:notes|indicates|states|shows)\s+", "", text, flags=re.I)
    text = re.sub(r"\b(?:on )?page\s+\d+\b", "", text, flags=re.I)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def create_conversation(language: str = "en") -> str:
    conversation_id = str(uuid.uuid4())
    with connection() as db:
        db.execute("INSERT INTO conversations VALUES (?,?,?,?)", (conversation_id, language, now(), now()))
    return conversation_id


def history(conversation_id: str) -> list[dict]:
    with connection() as db:
        exists = db.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not exists:
            raise ValueError("Conversation not found")
        return [dict(row) for row in db.execute("SELECT role, body, created_at FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))]


def save_message(conversation_id: str, role: str, body: str):
    with connection() as db:
        db.execute("INSERT INTO messages(conversation_id,role,body,created_at) VALUES (?,?,?,?)", (conversation_id, role, body, now()))
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), conversation_id))


def agent_functions(allow_write: bool):
    def retrieve_project_knowledge(question: str, project_id: str = "") -> dict:
        """Search assignment knowledge for a customer question and return excerpts with source pages."""
        return domain.retrieve_project_knowledge(question, project_id)

    def get_township_overview() -> dict:
        """Return documented township area, Phase 1, walk-to-work concept and infrastructure."""
        return domain.get_township_overview()

    def get_project_details(project_id: str) -> dict:
        """Get verified details for Project A or Project B. Use A or B as project_id."""
        return domain.get_project_details(project_id)

    def get_connectivity_information(destination: str = "") -> dict:
        """Get documented distances. Leave destination empty to list all."""
        return domain.get_connectivity_information(destination)

    def convert_plot_area(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert a positive area between sq yd, sq ft and sq m."""
        return domain.convert_plot_area(value, from_unit, to_unit)

    def compare_projects() -> dict:
        """Compare Project A and Project B using documented features only."""
        return domain.compare_projects()

    def calculate_property_values(area_sq_yd: float, price_per_sq_yd: float) -> dict:
        """Multiply supplied area and rate for an illustrative, non-binding amount in INR."""
        return domain.calculate_property_values(area_sq_yd, price_per_sq_yd)

    def capture_customer_lead(name: str, mobile: str = "", email: str = "", project: str = "", interest: str = "", budget: str = "", contact_time: str = "", requirements: str = "") -> dict:
        """Store a customer inquiry only if the customer explicitly enabled contact storage in this turn."""
        if not allow_write:
            return {"error": "Ask the customer to tick the consent box before storing contact details."}
        try:
            return domain.capture_customer_lead(domain.Lead(name=name, mobile=mobile or None, email=email or None, project=project or None, interest=interest or None, budget=budget or None, contact_time=contact_time or None, requirements=requirements or None, consent=True))
        except ValidationError as error:
            return {"error": str(error)}

    def create_site_visit_request(name: str, preferred_date: str, mobile: str = "", email: str = "", project: str = "", preferred_time: str = "") -> dict:
        """Record a requested site visit as pending confirmation; requires explicit contact-storage consent."""
        if not allow_write:
            return {"error": "Ask the customer to tick the consent box before storing a visit request."}
        try:
            return domain.create_site_visit_request(domain.Visit(name=name, preferred_date=preferred_date, mobile=mobile or None, email=email or None, project=project or None, preferred_time=preferred_time or None, consent=True))
        except ValidationError as error:
            return {"error": str(error)}

    def request_human_callback(name: str, mobile: str = "", email: str = "", note: str = "") -> dict:
        """Record a human callback request; requires explicit contact-storage consent."""
        if not allow_write:
            return {"error": "Ask the customer to tick the consent box before storing a callback request."}
        try:
            return domain.request_human_callback(domain.Callback(name=name, mobile=mobile or None, email=email or None, note=note or None, consent=True))
        except ValidationError as error:
            return {"error": str(error)}

    return [retrieve_project_knowledge, get_township_overview, get_project_details,
            get_connectivity_information, convert_plot_area, compare_projects,
            calculate_property_values, capture_customer_lead, create_site_visit_request,
            request_human_callback]


def chat(conversation_id: str, message: str, language: str = "en", consent_to_store: bool = False) -> dict:
    previous = history(conversation_id)[-12:]
    context_query = " ".join([row["body"] for row in previous if row["role"] == "user"][-2:] + [message])
    evidence = retrieve(context_query, limit=5)
    if not settings.allow_knowledge_export or not settings.gemini_api_key:
        if re.search(r"\b(availability|inventory|booking charges?|payment plans?|travel times?|guaranteed? returns?)\b", message, re.I):
            answer = "Current availability, booking charges, payment plans and travel times are not confirmed. A sales team member would need to verify current details. Investment returns are not guaranteed."
        elif evidence:
            best = evidence[0]
            answer = best["text"]
        else:
            answer = "I don't have confirmed information to answer that question."
        answer = customer_answer(answer)
        save_message(conversation_id, "user", message)
        save_message(conversation_id, "assistant", answer)
        return {"conversation_id": conversation_id, "answer": answer, "mode": "local_reference",
                "sources": [{"source": x["source"], "page": x["page"], "section": x["section"]} for x in evidence]}
    context = "\n\n".join(f"[{x['source']}, page {x['page']}, {x['section']}] {x['text']}" for x in evidence)
    instruction = PROMPT + f"\nPreferred language: {language}.\nRetrieved evidence for the current turn:\n{context or 'No matching evidence found. Do not guess.'}"
    contents = [types.Content(role="user" if row["role"] == "user" else "model", parts=[types.Part(text=row["body"])]) for row in previous]
    client = genai.Client(api_key=settings.gemini_api_key)
    chat_session = client.chats.create(
        model=settings.chat_model, history=contents,
        config=types.GenerateContentConfig(
            system_instruction=instruction, tools=agent_functions(consent_to_store),
            temperature=settings.temperature, max_output_tokens=settings.max_output_tokens,
        ),
    )
    response = chat_session.send_message(message)
    answer = customer_answer(response.text or "")
    if not answer:
        raise RuntimeError("Gemini returned no answer. Please retry.")
    save_message(conversation_id, "user", message)
    save_message(conversation_id, "assistant", answer)
    return {"conversation_id": conversation_id, "answer": answer, "mode": "gemini",
            "sources": [{"source": x["source"], "page": x["page"], "section": x["section"]} for x in evidence]}

