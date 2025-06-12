import uuid
from fastapi import APIRouter, HTTPException
from datetime import date, datetime
import pytz

from models.schema import BloodBiomarkerInput, BloodBioMarker, fetch_patient_name, resolve_added_by_name
from routers.doctor_assignments import is_doctor_assigned, auto_assign_reviewer
from firebase_config import db

router = APIRouter(prefix="/biomarkers", tags=["Blood BioMarkers"])
egypt_tz = pytz.timezone("Africa/Cairo")

# === Helpers ===
def convert_dates(obj):
    if isinstance(obj, dict):
        return {k: convert_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates(v) for v in obj]
    elif isinstance(obj, date) and not isinstance(obj, datetime):
        return datetime.combine(obj, datetime.min.time())
    else:
        return obj

def is_valid_facility_or_doctor(added_by_id: str) -> bool:
    # Facility by ID
    facilities = db.collection("Facilities").where("facility_id", "==", added_by_id).stream()
    if any(True for _ in facilities):
        return True

    # Doctor by ID
    doctors = db.collection("Doctors").where("doctor_id", "==", added_by_id).stream()
    if any(True for _ in doctors):
        return True

    return False

def store_procedure_under_facility(facility_id: str, patient_id: str, procedure_type: str, procedure_data: dict):
    facility_docs = db.collection("Facilities").where("facility_id", "==", facility_id).stream()
    facility_doc = next(facility_docs, None)
    if not facility_doc:
        return

    # ❗ Correct way: use document ID (which is the facility name)
    facility_doc_id = facility_doc.id

    timestamp = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    db.collection("Facilities").document(facility_doc_id) \
        .collection("PatientsMadeProcedures").document(patient_id) \
        .collection(procedure_type).document(timestamp).set(procedure_data)


# === POST biomarker ===
@router.post("/{national_id}")
def add_biomarker(national_id: str, entry: BloodBiomarkerInput):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    entry_dict = convert_dates(entry.dict())

    # ✅ Direct add (from registered facility or doctor)
    if is_valid_facility_or_doctor(entry.added_by):
        if entry_dict.get("date") is None:
            entry_dict["date"] = date.today()

        full_record = BloodBioMarker(
            **entry_dict,
            added_by_name=resolve_added_by_name(entry.added_by),
            patient_name=fetch_patient_name(user_ref),
        )

        timestamp_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

        # Save in patient's medical records
        db.collection("Users").document(national_id) \
            .collection("ClinicalIndicators").document("bloodbiomarkers") \
            .collection("Records").document(timestamp_id) \
            .set(convert_dates(full_record.dict()))

        # Save under facility subcollection
        store_procedure_under_facility(entry.added_by, national_id, "bloodbiomarkers", convert_dates(full_record.dict()))

        return {
            "message": "✅ Biomarker added directly by facility or doctor",
            "added_by": entry.added_by
        }

    # ✅ Fallback approval flow
    doctor_name = is_doctor_assigned(national_id)
    assigned_to = None

    if doctor_name:
        doctor_ref = db.collection("Doctors").document(doctor_name)
        if doctor_ref.get().exists:
            assigned_to = doctor_name  # Registered doctor
        else:
            assigned_to = doctor_name  # Unregistered doctor (still fallback)
    else:
        auto = auto_assign_reviewer(national_id)
        assigned_to = auto["assigned_to"]

    doc_id = uuid.uuid4().hex
    db.collection("PendingApprovals").document(assigned_to).collection("bloodbiomarkers").document(doc_id).set({
        "national_id": national_id,
        "record": entry_dict,
        "data_type": "bloodbiomarkers",
        "assigned_to": assigned_to,
        "assigned_doctor_name": doctor_name,
        "submitted_at": datetime.now(egypt_tz).isoformat()
    })

    return {
        "status": "submitted_for_approval",
        "assigned_to": assigned_to,
        "doc_id": doc_id
    }

# === GET biomarkers for a patient ===
@router.get("/{national_id}")
def get_biomarkers(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("ClinicalIndicators").document("bloodbiomarkers").collection("Records").stream()
    return [doc.to_dict() for doc in docs]
