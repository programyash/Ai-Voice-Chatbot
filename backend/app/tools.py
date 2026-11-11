"""Validated agent tools. Write operations require UI-confirmed consent."""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel, Field, model_validator

from .db import connection, now
from .knowledge import retrieve

TOWNSHIP = {
    "area_acres_approx": 8250, "phase_1_acres_approx": 2400, "phase_1_sectors": 11,
    "concept": "walk-to-work; residential, commercial, industrial and social infrastructure",
    "infrastructure": ["dedicated power substations", "underground electricity", "smart street lighting", "50 MLD water treatment plant", "100 MLD water allocation", "sewage treatment and recycling", "professionally managed maintenance"],
    "source": "Assignment - AI Voice Bot Development.pdf, page 1",
}
PROJECTS = {
    "A": {"name": "Premium Villa Plots", "area_acres_approx": 25, "type": "gated residential villa plots", "plot_count": "more than 100", "plot_size_sq_yd": [267, 597], "amenities": ["jogging tracks", "cycling tracks", "tennis", "badminton", "skating rink", "children's play area", "amphitheatre", "gazebo", "meditation plaza", "four parks"], "green_space": "approximately 50% green and open landscape", "ownership": "freehold", "club": "complimentary township club access", "education_healthcare": "near educational and healthcare facilities", "source": "Assignment - AI Voice Bot Development.pdf, pages 1-2"},
    "B": {"name": "Integrated Mixed-Use Development", "area_acres_approx": 138.76, "type": "residential plots and commercial development", "residential_acres_approx": 80, "commercial_acres_approx": 35, "business_plots_approx": 85, "amenities": ["parks", "open-air gym", "children's play area", "cricket pitch", "gazebo", "commercial facilities", "club facilities"], "green_space": "more than 5 acres of green spaces", "education": "nursery and primary school planned inside; more than 15 institutions nearby", "healthcare": "8 hospitals and clinics nearby", "banking": "major facilities within approximately 1 km", "source": "Assignment - AI Voice Bot Development.pdf, page 2"},
}
DISTANCES = {"IGI Airport": 45, "Gurugram": 30, "KMP Expressway": 11, "Dwarka Expressway": 22, "Farrukhnagar Railway Station": 6}


class Contact(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    mobile: str | None = None
    email: str | None = None
    consent: bool

    @model_validator(mode="after")
    def valid_contact(self):
        if not self.consent:
            raise ValueError("Explicit consent is required")
        if not self.mobile and not self.email:
            raise ValueError("Provide a mobile number or email")
        if self.mobile and not re.fullmatch(r"\+?[0-9][0-9\s-]{7,17}", self.mobile):
            raise ValueError("Invalid mobile number")
        if self.email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email):
            raise ValueError("Invalid email address")
        return self


class Lead(Contact):
    project: str | None = None
    interest: str | None = None
    budget: str | None = None
    contact_time: str | None = None
    requirements: str | None = None


class Visit(Contact):
    project: str | None = None
    preferred_date: date
    preferred_time: str | None = None

    @model_validator(mode="after")
    def future_date(self):
        if self.preferred_date < date.today():
            raise ValueError("Preferred date must be today or later")
        return self


class Callback(Contact):
    note: str | None = None


def retrieve_project_knowledge(question: str, project_id: str = "") -> dict:
    """Search the township knowledge base and return relevant excerpts with page citations."""
    return {"results": retrieve(question, project_id.upper() or None)}


def get_township_overview() -> dict:
    """Return verified township acreage, phase, concept and infrastructure."""
    return TOWNSHIP


def get_project_details(project_id: str) -> dict:
    """Get documented facts for Project A or Project B. project_id must be A or B."""
    key = project_id.strip().upper()
    if key not in PROJECTS:
        return {"error": "Unknown project. Choose A or B."}
    return {"project_id": key, **PROJECTS[key]}


def get_connectivity_information(destination: str = "") -> dict:
    """Return assignment-provided distances in km; no travel times are available."""
    if not destination:
        return {"distances_km_approx": DISTANCES, "other": "Dedicated Freight Corridor; Haryana Orbital Rail Corridor is proposed", "source": "Assignment PDF, page 1"}
    matches = {k: v for k, v in DISTANCES.items() if destination.lower() in k.lower() or k.lower() in destination.lower()}
    return {"distances_km_approx": matches, "source": "Assignment PDF, page 1"} if matches else {"error": "Distance not specified in the assignment"}


def convert_plot_area(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert a positive plot area between square yards, square feet and square metres."""
    factors = {"sq yd": 1.0, "square yards": 1.0, "sq ft": 1 / 9, "square feet": 1 / 9, "sq m": 1 / 0.83612736, "square metres": 1 / 0.83612736}
    a, b = from_unit.lower().strip(), to_unit.lower().strip()
    if value <= 0 or a not in factors or b not in factors:
        return {"error": "Use a positive value and supported units: sq yd, sq ft, sq m"}
    return {"input": value, "from_unit": from_unit, "result": round(value * factors[a] / factors[b], 4), "to_unit": to_unit}


def compare_projects() -> dict:
    """Compare Project A and B on documented fields only."""
    return {"A": PROJECTS["A"], "B": PROJECTS["B"], "note": "Project B plot size and ownership type are not specified; no current inventory or price is provided."}


def calculate_property_values(area_sq_yd: float, price_per_sq_yd: float) -> dict:
    """Multiply customer-provided area and price for an illustrative total, not an official quotation."""
    if area_sq_yd <= 0 or price_per_sq_yd <= 0 or area_sq_yd > 1_000_000 or price_per_sq_yd > 1_000_000_000:
        return {"error": "Provide positive, reasonable area and rate values"}
    return {"illustrative_total_inr": round(area_sq_yd * price_per_sq_yd, 2), "area_sq_yd": area_sq_yd, "price_per_sq_yd_inr": price_per_sq_yd, "disclaimer": "Illustrative arithmetic only; this is not a current price or quotation."}


def capture_customer_lead(data: Lead) -> dict:
    """Persist a consented customer inquiry."""
    lead_id = str(uuid.uuid4())
    with connection() as db:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        duplicate = db.execute("SELECT id FROM leads WHERE name=? AND (mobile=? OR email=?) AND created_at > ?", (data.name, data.mobile, str(data.email) if data.email else None, cutoff)).fetchone()
        if duplicate:
            return {"id": duplicate[0], "status": "already received"}
        db.execute("INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?)", (lead_id, data.name, data.mobile, str(data.email) if data.email else None, data.project, data.interest, data.budget, data.contact_time, data.requirements, now(), now()))
    return {"id": lead_id, "status": "inquiry received"}


def create_site_visit_request(data: Visit) -> dict:
    """Record a site visit request pending confirmation; never claim it is booked."""
    visit_id = str(uuid.uuid4())
    with connection() as db:
        db.execute("INSERT INTO visits VALUES (?,?,?,?,?,?,?,?,?)", (visit_id, data.project, data.preferred_date.isoformat(), data.preferred_time, data.name, data.mobile, str(data.email) if data.email else None, "pending confirmation", now()))
    return {"id": visit_id, "status": "pending confirmation"}


def request_human_callback(data: Callback) -> dict:
    """Record a request for a human callback without promising a time."""
    callback_id = str(uuid.uuid4())
    with connection() as db:
        db.execute("INSERT INTO callbacks VALUES (?,?,?,?,?,?,?)", (callback_id, data.name, data.mobile, str(data.email) if data.email else None, data.note, "pending", now()))
    return {"id": callback_id, "status": "pending"}

