from fastapi import APIRouter, HTTPException
from models.schema import DiagnosisEntry, DiagnosisCreate
from firebase_config import db
from datetime import datetime
from uuid import uuid4
import pytz

router = APIRouter(prefix="/diagnoses", tags=["Diagnoses"])
egypt_tz = pytz.timezone("Africa/Cairo")


# ---------------------- Add Diagnosis ----------------------
@router.post("/{national_id}")
def add_diagnosis(national_id: str, entry: DiagnosisCreate):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    record_id = str(uuid4())
    timestamp = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    data = entry.dict()
    dt = datetime.strptime(entry.diagnosis_date, "%Y-%m-%d")
    data["diagnosis_date"] = dt.strftime("%Y-%m-%d")
    data["timestamp"] = timestamp
    data["id"] = record_id
    data["user_id"] = national_id

    user_ref.collection("diagnoses").document(record_id).set(data)
    return {"message": "Diagnosis added", "record_id": record_id}


# ---------------------- Get Diagnoses ----------------------
@router.get("/{national_id}")
def get_diagnoses(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("diagnoses").stream()
    return [{**doc.to_dict(), "id": doc.id} for doc in docs]


# ---------------------- Update Diagnosis ----------------------
@router.put("/{national_id}/{record_id}")
def update_diagnosis(national_id: str, record_id: str, entry: DiagnosisCreate):
    record_ref = db.collection("Users").document(national_id).collection("diagnoses").document(record_id)
    doc = record_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    # ✅ Check permission
    if doc.to_dict().get("added_by") != entry.added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this diagnosis.")

    data = entry.dict()
    dt = datetime.strptime(entry.diagnosis_date, "%Y-%m-%d")
    data["diagnosis_date"] = dt.strftime("%Y-%m-%d")
    data["timestamp"] = doc.to_dict().get("timestamp")  # Preserve original timestamp
    data["id"] = record_id
    data["user_id"] = national_id

    record_ref.set(data)
    return {"message": "Diagnosis updated", "record_id": record_id}


# ---------------------- Delete Diagnosis ----------------------
@router.delete("/{national_id}/{record_id}")
def delete_diagnosis(national_id: str, record_id: str, added_by: str):
    record_ref = db.collection("Users").document(national_id).collection("diagnoses").document(record_id)
    doc = record_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this diagnosis.")

    record_ref.delete()
    return {"message": "Diagnosis deleted", "record_id": record_id}
