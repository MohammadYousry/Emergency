from fastapi import APIRouter, HTTPException
from datetime import date, datetime
import pytz, uuid

from models.schema import RadiologyTest, RadiologyTestInput, resolve_added_by_name, fetch_patient_name
from routers.doctor_assignments import is_doctor_assigned, auto_assign_reviewer
from firebase_config import db

router = APIRouter(prefix="/radiology", tags=["Radiology"])
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
    facilities = db.collection("Facilities").where("facility_id", "==", added_by_id).stream()
    if any(True for _ in facilities):
        return True

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


# === POST radiology ===
@router.post("/{national_id}")
def add_radiology(national_id: str, entry: RadiologyTestInput):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    entry_dict = convert_dates(entry.dict())

    # ✅ Direct add (from registered doctor/facility)
    if is_valid_facility_or_doctor(entry.added_by):
        if entry_dict.get("date") is None:
            entry_dict["date"] = date.today()

        full_record = RadiologyTest(
            **entry_dict,
            added_by_name=resolve_added_by_name(entry.added_by),
            patient_name=fetch_patient_name(user_ref),
        )

        timestamp_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

        db.collection("Users").document(national_id) \
            .collection("ClinicalIndicators").document("radiology") \
            .collection("Records").document(timestamp_id) \
            .set(convert_dates(full_record.dict()))

        store_procedure_under_facility(entry.added_by, national_id, "radiology", convert_dates(full_record.dict()))

        return {
            "message": "✅ Radiology record added directly by facility or doctor",
            "added_by": entry.added_by
        }

    # ✅ Fallback approval flow
    doctor_name = is_doctor_assigned(national_id)
    assigned_to = None

    if doctor_name:
        doctor_ref = db.collection("Doctors").document(doctor_name)
        if doctor_ref.get().exists:
            assigned_to = doctor_name
        else:
            assigned_to = doctor_name
    else:
        auto = auto_assign_reviewer(national_id)
        assigned_to = auto["assigned_to"]

    doc_id = uuid.uuid4().hex
    db.collection("PendingApprovals").document(assigned_to).collection("radiology").document(doc_id).set({
        "national_id": national_id,
        "record": entry_dict,
        "data_type": "radiology",
        "assigned_to": assigned_to,
        "assigned_doctor_name": doctor_name,
        "submitted_at": datetime.now(egypt_tz).isoformat()
    })

    return {
        "status": "submitted_for_approval",
        "assigned_to": assigned_to,
        "doc_id": doc_id
    }

# === GET radiology records for a patient ===
@router.get("/{national_id}")
def get_radiology(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("ClinicalIndicators").document("radiology").collection("Records").stream()
    return [doc.to_dict() for doc in docs]
