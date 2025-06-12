from fastapi import APIRouter, HTTPException, Form
from datetime import datetime
import os
import qrcode
from firebase_admin import firestore
from firebase_config import db, bucket
from models.schema import (
    QRCodeResponse,
    QRCodeWithUserInfoResponse,
    UserEmergencyInfo
)

router = APIRouter(prefix="/qrcode", tags=["QR Codes"])

# 📁 مرجع Firestore لمستند QR
def get_qr_code_doc_ref(user_id: str):
    return db.collection("Users").document(user_id).collection("QRCodeAccess").document("single_qr_code")

# 🧠 توليد صورة QR ورفعها إلى Firebase Storage
def generate_qr_image(user_id: str) -> str:
    try:
        qr_url = f"https://medigo-eg.netlify.app/card/emergency_card.html?user_id={user_id}"
        local_folder = f"./qr_images/{user_id}"
        os.makedirs(local_folder, exist_ok=True)
        local_file_path = os.path.join(local_folder, f"{user_id}_qrcode.png")

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(local_file_path)

        blob = bucket.blob(f"qr_codes/{user_id}_qrcode.png")
        blob.upload_from_filename(local_file_path)
        blob.make_public()

        os.remove(local_file_path)
        return blob.public_url

    except Exception as e:
        print(f"❌ [generate_qr_image] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"QR generation failed: {str(e)}")

# 🌐 إنشاء QR جديد
@router.post("/", response_model=QRCodeResponse)
async def create_qr_code(
    user_id: str = Form(...),
    expiration_date: str = Form(...)
):
    try:
        user_doc = db.collection("Users").document(user_id).get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        image_url = generate_qr_image(user_id)
        now_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        web_url = f"https://medigo-eg.netlify.app/card/emergency_card.html?user_id={user_id}"

        qr_data_to_store = {
            "user_id": user_id,
            "last_accessed": now_timestamp,
            "expiration_date": expiration_date,
            "qr_image": image_url,
            "qr_data": web_url,
            "image_url": image_url
        }

        get_qr_code_doc_ref(user_id).set(qr_data_to_store)
        return QRCodeResponse(**qr_data_to_store)

    except Exception as e:
        print(f"❌ [create_qr_code] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating QR code: {str(e)}")

@router.get("/{user_id}", response_model=QRCodeWithUserInfoResponse)
def get_user_info_by_qr(user_id: str):
    user_doc = db.collection("Users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_doc.to_dict()

    # ✅ الدالة الجديدة والمحسّنة
    def get_collection(path):
        """Fetches all documents from a given collection path."""
        try:
            return [doc.to_dict() for doc in path.stream()]
        except Exception as e:
            print(f"Warning: Could not fetch collection at {path.path}. Error: {e}")
            return []

    # ✅ استدعاءات نظيفة ومباشرة لكل البيانات من الـ sub-collections
    user_data["surgeries"] = get_collection(db.collection("Users").document(user_id).collection("surgeries"))
    user_data["radiology"] = get_collection(db.collection("Users").document(user_id).collection("ClinicalIndicators").document("radiology").collection("Records"))
    user_data["biomarkers"] = get_collection(db.collection("Users").document(user_id).collection("ClinicalIndicators").document("bloodbiomarkers").collection("Records"))
    # ✅ الحساسية
    user_data["allergies"] = get_collection(db.collection("Users").document(user_id).collection("allergies"))
    # ✅ سنضيف أمر طباعة هنا لنرى ماذا قرأ الكود بالضبط
    print(f"DEBUG_ALLERGY_READ: Fetched allergies for user '{user_id}'. Data: {user_data['allergies']}")
    # ✅ الأدوية
    user_data["medications"] = get_collection(db.collection("Users").document(user_id).collection("medications"))
    user_data["emergency_contacts"] = get_collection(db.collection("Users").document(user_id).collection("emergency_contacts"))
    user_data["diagnoses"] = get_collection(db.collection("Users").document(user_id).collection("diagnoses"))
    user_data["family_history"] = get_collection(db.collection("Users").document(user_id).collection("family_history"))
    
    # ✅ الأمراض المزمنة (من المستند الرئيسي)
    user_data["chronic_diseases"] = user_data.get("chronic_diseases", [])

    # ✅ منطق ضغط الدم (بقي كما هو)
    bp_docs = list(db.collection("Users").document(user_id)
        .collection("ClinicalIndicators")
        .document("Hypertension")
        .collection("Records")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream())

    user_data["hypertension_stage"] = "غير متوفر" # قيمة افتراضية
    if bp_docs:
        latest_bp = bp_docs[0].to_dict()
        systolic = latest_bp.get("systolic")
        diastolic = latest_bp.get("diastolic")

        def classify_bp_stage(sys, dia):
            if sys >= 180 or dia >= 120: return "Stage 3 - Hypertensive Crisis"
            if sys >= 140 or dia >= 90: return "Stage 2 - Hypertension"
            if sys >= 130 or dia >= 80: return "Stage 1 - Hypertension"
            if sys >= 120 and dia < 80: return "Elevated"
            return "Normal"

        if systolic and diastolic:
            user_data["hypertension_stage"] = classify_bp_stage(systolic, diastolic)

    # ✅ صورة البروفايل
    user_data["profile_photo"] = (
        user_data.get("profile_picture_url") or
        user_data.get("profile_photo") or
        user_data.get("profile_image") or
        "https://medigo-eg.netlify.app/medi_go_logo.png"  # Fallback
    )
    
    # ✅ إرجاع البيانات باستخدام النموذج الصحيح
    return QRCodeWithUserInfoResponse(
        user_id=user_id,
        user_info=user_data 
    )
