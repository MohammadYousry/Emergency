from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from typing import Optional
from firebase_config import db
from models.schema import DoctorAssignmentCreate

router = APIRouter(prefix="/doctor-assignments", tags=["Doctor Assignments"])

# 📌 Assign a doctor (registered or not)
@router.post("/")
def assign_doctor(assignment: DoctorAssignmentCreate):
    assigned_to = "admin"
    doctor_registered = False
    assignment_id = str(uuid4())  # ✅ generate unique ID

    doctor_query = db.collection("Doctors").where("email", "==", assignment.doctor_email).limit(1).stream()
    doctor_doc = next(doctor_query, None)

    doc_id = f"{assignment.doctor_email}_{assignment.patient_national_id}"

    if doctor_doc:
        assigned_to = assignment.doctor_email
        doctor_registered = True
        db.collection("Doctors").document(assignment.doctor_email) \
            .collection("AssignedPatients") \
            .document(assignment.patient_national_id).set({
                "patient_national_id": assignment.patient_national_id,
                "assigned_at": datetime.now().isoformat()
            })
    else:
        db.collection("DoctorAssignments").document(doc_id).set({
            "assignment_id": assignment_id,
            "doctor_email": assignment.doctor_email,
            "doctor_name": getattr(assignment, "doctor_name", "Unknown"),
            "patient_national_id": assignment.patient_national_id,
            "assigned_to": assigned_to,
            "assignment_date": assignment.assignment_date,
            "notes": assignment.notes
        })

        db.collection("AdminNotifications").document("unregistered_doctors") \
            .collection("Notifications").document(doc_id).set({
                "patient_national_id": assignment.patient_national_id,
                "doctor_email": assignment.doctor_email,
                "message": f"⚠️ Patient {assignment.patient_national_id} was assigned to '{assignment.doctor_email}', who is NOT registered.",
                "timestamp": datetime.now().isoformat()
            })

    return {
        "assigned_to": assigned_to,
        "assignment_id": assignment_id,
        "message": f"Doctor {assignment.doctor_email} assigned to patient {assignment.patient_national_id}",
        "admin_alert": None if doctor_registered else "Unregistered doctor — admin notified"
    }


# 📌 Check if doctor assigned
@router.get("/check")
def check_doctor(patient_national_id: str):
    docs = db.collection("DoctorAssignments") \
        .where("patient_national_id", "==", patient_national_id) \
        .stream()

    for doc in docs:
        doctor_email = doc.to_dict().get("doctor_email")
        if doctor_email:
            doctor_doc = db.collection("Doctors").document(doctor_email).get()
            if doctor_doc.exists:
                doctor_data = doctor_doc.to_dict()
                return {
                    "email": doctor_email,
                    "name": doctor_data.get("doctor_name", "Unknown")
                }

    doctors = db.collection("Doctors").stream()
    for doctor in doctors:
        doctor_email = doctor.id
        assigned_doc = db.collection("Doctors") \
            .document(doctor_email) \
            .collection("AssignedPatients") \
            .document(patient_national_id).get()
        if assigned_doc.exists:
            doctor_data = db.collection("Doctors").document(doctor_email).get().to_dict()
            return {
                "email": doctor_email,
                "name": doctor_data.get("doctor_name", "Unknown")
            }

    raise HTTPException(status_code=404, detail="No doctor assigned to this patient.")


# 📌 Auto-assign fallback reviewer by region
def auto_assign_reviewer(patient_national_id: str) -> dict:
    user_ref = db.collection("Users").document(patient_national_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict()
    user_region = user_data.get("region", "").strip().lower()

    facility_query = db.collection("Facilities") \
        .where("region", "==", user_region) \
        .where("role", "==", "hospital") \
        .limit(1).stream()
    facility_doc = next(facility_query, None)
    if facility_doc:
        return {"assigned_to": facility_doc.id, "assigned_type": "facility"}

    doctor_query = db.collection("Doctors") \
        .where("region", "==", user_region).limit(1).stream()
    doctor_doc = next(doctor_query, None)
    if doctor_doc:
        return {"assigned_to": doctor_doc.id, "assigned_type": "doctor"}

    return {"assigned_to": "admin", "assigned_type": "admin"}


# 📌 Get all patients assigned to a doctor
@router.get("/{doctor_email}/patients")
def get_patients_for_doctor(doctor_email: str):
    assignments = db.collection("DoctorAssignments") \
        .where("doctor_email", "==", doctor_email).stream()
    
    patients = [doc.to_dict() for doc in assignments]

    doctor_ref = db.collection("Doctors").document(doctor_email)
    if doctor_ref.get().exists:
        assigned = doctor_ref.collection("AssignedPatients").stream()
        patients += [doc.to_dict() for doc in assigned]

    return patients
# 📌 Simple helper to get assigned doctor email if registered or in fallback
def is_doctor_assigned(national_id: str) -> Optional[str]:
    doc_ref = db.collection("DoctorAssignments") \
        .where("patient_national_id", "==", national_id) \
        .limit(1).stream()
    for doc in doc_ref:
        return doc.to_dict().get("doctor_email")

    # Check inside registered doctors
    doctors = db.collection("Doctors").stream()
    for doctor in doctors:
        assigned_doc = db.collection("Doctors") \
            .document(doctor.id) \
            .collection("AssignedPatients") \
            .document(national_id).get()
        if assigned_doc.exists:
            return doctor.id

    return None
