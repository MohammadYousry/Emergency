from fastapi import APIRouter, HTTPException, Request
from models.schema import HypertensionCreate # تم تعديل الـ import
from firebase_config import db
from datetime import datetime
import pytz

egypt_tz = pytz.timezone("Africa/Cairo")
router = APIRouter(prefix="/hypertension", tags=["Hypertension"])

@router.post("/{national_id}")
def add_bp(national_id: str, entry: HypertensionCreate):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    timestamp_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    systolic = entry.readings.systolic
    diastolic = entry.readings.diastolic
    pulse = entry.readings.pulse
    
    # ✅ بناء القاموس data بشكل صحيح
    data = entry.dict() # ابدأ ببيانات المستخدم
    data["systolic"] = systolic
    data["diastolic"] = diastolic
    data["pulse"] = pulse
    data["pulse_pressure"] = systolic - diastolic
    data["timestamp"] = timestamp_id
    data["id"] = timestamp_id # استخدام الـ timestamp كـ id

    # ❌ تم حذف الحقول التي لم تعد موجودة في entry

    user_ref.collection("ClinicalIndicators").document("Hypertension").collection("Records").document(timestamp_id).set(data)
    return {"message": "Blood pressure record added", "id": timestamp_id}


@router.put("/{national_id}/{record_id}")
def update_bp(national_id: str, record_id: str, entry: HypertensionCreate):
    record_ref = db.collection("Users").document(national_id).collection("ClinicalIndicators").document("Hypertension").collection("Records").document(record_id)
    doc = record_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    # ✅ تعديل التحقق من الصلاحية
    if doc.to_dict().get("added_by") != entry.added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this record")

    systolic = entry.readings.systolic
    diastolic = entry.readings.diastolic

    record_ref.update({
        "systolic": systolic,
        "diastolic": diastolic,
        "pulse": entry.readings.pulse,
        "pulse_pressure": systolic - diastolic,
        "position": entry.position,
        "notes": entry.notes,
        "reading_date": entry.reading_date
    })
    return {"message": "Blood pressure record updated", "id": record_id}

# ... دوال GET و DELETE تبقى كما هي ...

@router.get("/{national_id}")
def get_bp(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records").stream()

    return [{**doc.to_dict(), "id": doc.id} for doc in docs]


@router.delete("/{national_id}/{record_id}")
def delete_bp(national_id: str, record_id: str, request: Request):
    added_by = request.query_params.get("added_by")

    record_ref = db.collection("Users") \
        .document(national_id) \
        .collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records") \
        .document(record_id)

    doc = record_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this record")

    record_ref.delete()
    return {"message": "Record deleted", "id": record_id}
