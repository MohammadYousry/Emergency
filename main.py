from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
import secrets
import logging

# ✅ Logging بدل من print
logging.basicConfig(level=logging.INFO)
logging.info("✅ FastAPI MediGO backend is starting...")

# ✅ تأكد من تحميل Firebase Config
import firebase_config

# === Routers ===
from routers import (
    users, pending_approvals, doctor_assignments,
    surgeries, bloodbiomarkers, measurements, radiology, hypertension,
    medications, diagnoses, allergies, family_history,
    emergency_contacts, risk_assessment, admin, user_role, auth, facilities, qrcode,
)

# === Create FastAPI App (hide default docs) ===
app = FastAPI(
    title="MediGO Backend",
    version="1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json"
)

# === CORS Middleware ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Include Routers ===
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(qrcode.router)
app.include_router(pending_approvals.router)
app.include_router(doctor_assignments.router)
app.include_router(facilities.router)
app.include_router(surgeries.router)
app.include_router(bloodbiomarkers.router)
app.include_router(measurements.router)
app.include_router(radiology.router)
app.include_router(hypertension.router)
app.include_router(medications.router)
app.include_router(diagnoses.router)
app.include_router(allergies.router)
app.include_router(family_history.router)
app.include_router(emergency_contacts.router)
app.include_router(risk_assessment.router)
app.include_router(user_role.router)

# === Root Endpoint ===
@app.get("/")
def root():
    return {"message": "Welcome to the MediGO FastAPI Backend"}

# === Secure Swagger UI (/docs) ===
security = HTTPBasic()

def verify_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "admin")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/docs", include_in_schema=False)
def custom_swagger_ui(credentials: bool = Depends(verify_docs_credentials)):
    return get_swagger_ui_html(openapi_url=app.openapi_url, title="MediGO Docs")

# === Custom 404 Error Response ===
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"message": "❌ Endpoint not found. Please check the URL."}
    )

# === Run Locally ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
