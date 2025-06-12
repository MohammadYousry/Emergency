from fastapi import APIRouter, HTTPException
from models.schema import HeightWeightCreate
from firebase_config import db
from datetime import datetime
import pytz

router = APIRouter(prefix="/measurements", tags=["Measurements"])
egypt_tz = pytz.timezone("Africa/Cairo")

# === 1. Add Height & Weight ===
@router.post("/body/{national_id}")
def add_height_weight(national_id: str, entry: HeightWeightCreate):
    height = entry.height_cm
    weight = entry.weight_kg
    bmi = entry.bmi

    if not height or not weight:
        raise HTTPException(status_code=400, detail="Height and weight are required")

    # If BMI not provided, calculate it
    if not bmi:
        bmi = round(weight / ((height / 100) ** 2), 2)

    user_ref = db.collection("Users").document(national_id)

    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    data = {
        "height_cm": height,
        "weight_kg": weight,
        "bmi": bmi,
        "notes": entry.notes,
        "measurement_date": entry.measurement_date,
        "created_at": datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    }

    user_ref.collection("ClinicalIndicators").document("measurements").set(data)
    return {"message": "✅ Height, weight, and BMI saved", "bmi": bmi}


# === 2. Get Height & Weight ===
@router.get("/body/{national_id}")
def get_height_weight(national_id: str):
    doc = db.collection("Users").document(national_id).collection("ClinicalIndicators").document("measurements").get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Body measurements not found")
    return doc.to_dict()
