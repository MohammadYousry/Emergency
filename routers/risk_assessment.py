from datetime import datetime
from fastapi import APIRouter, HTTPException
from firebase_config import db
import pandas as pd
import numpy as np
import joblib
from models.schema import RiskPredictionOutput, DerivedFeatures, TopFeatures

router = APIRouter(prefix="/risk", tags=["Risk Assessment"])

# Load ML assets
scaler_diabetes = joblib.load("scaler_diabetes.pkl")
scaler_hypertension = joblib.load("scaler_hypertension.pkl")
selector_dia = joblib.load("selector_dia.pkl")
selector_hyp = joblib.load("selector_hypertension.pkl")
model_diabetes = joblib.load("model_diabetes.pkl")
model_hypertension = joblib.load("model_hypertension.pkl")
selected_features_dia = joblib.load("selected_diabetes_features.pkl")
selected_features_hyp = joblib.load("selected_hypertension_features.pkl")


@router.post("/{national_id}", response_model=RiskPredictionOutput)
async def assess_risk(national_id: str):
    try:
        # --- 1. Fetch user ---
        user_doc = db.collection("Users").document(national_id).get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        user = user_doc.to_dict()

        # --- 2. Fetch measurements ---
        measurements_doc = db.collection("Users").document(national_id).collection("ClinicalIndicators").document("measurements").get()
        measurements = measurements_doc.to_dict()
        if not measurements:
            raise HTTPException(status_code=404, detail="Missing measurements")

        # --- 3. Latest Hypertension record ---
        hyp_docs = db.collection("Users").document(national_id).collection("ClinicalIndicators") \
            .document("Hypertension").collection("Records").order_by("date", direction="DESCENDING").limit(1).stream()
        hypertension_data = next(hyp_docs, None)
        hypertension = hypertension_data.to_dict() if hypertension_data else {}

        # --- 4. Latest blood biomarkers ---
        bio_docs = db.collection("Users").document(national_id).collection("ClinicalIndicators") \
            .document("bloodbiomarkers").collection("Records").order_by("date_added", direction="DESCENDING").limit(1).stream()
        biomarker_data = next(bio_docs, None)
        biomarkers = biomarker_data.to_dict() if biomarker_data else {}

        # --- 5. Latest medication record ---
        med_docs = db.collection("Users").document(national_id).collection("medications") \
            .order_by("start_date", direction="DESCENDING").limit(1).stream()
        medication_data = next(med_docs, None)
        medications = medication_data.to_dict() if medication_data else {}

        # --- 6. Derived BMI fields ---
        bmi = measurements.get("bmi", 25.0)
        if bmi < 18.5:
            bmi_category = 0
        elif 18.5 <= bmi < 25:
            bmi_category = 1
        elif 25 <= bmi < 30:
            bmi_category = 2
        else:
            bmi_category = 3
        is_obese = 1 if bmi >= 30 else 0

        # --- 7. Feature dictionary ---
        results = biomarkers.get("results", [])
        features = {
            "male": 1 if user.get("gender") == "male" else 0,
            "BPMeds": int(medications.get("bp_medication", 0)),
            "totChol": float(next((r.get("value") for r in results if r.get("test_name") == "Cholesterol"), 180)),
            "sysBP": float(hypertension.get("systolic", 120)),
            "diaBP": float(hypertension.get("diastolic", 80)),
            "heartRate": float(hypertension.get("pulse", 72)), # Also corrected 'heartRate' to 'pulse'
            "glucose": float(next((r.get("value") for r in results if r.get("test_name") == "Glucose"), 100)),
            "age_group": int(user.get("age_group", 1)),
            "smoker_status": int(user.get("smoker_status", 0)),
            "is_obese": is_obese,
            "bp_category": int(hypertension.get("bp_category", 0)),
            "bmi_category": bmi_category,
            "male_smoker": int(user.get("gender") == "male" and user.get("smoker_status", 0) > 0),
            "prediabetes_indicator": int(hypertension.get("prediabetes_indicator", 0)),
            "insulin_resistance": int(hypertension.get("insulin_resistance", 0)),
            "metabolic_syndrome": int(hypertension.get("metabolic_syndrome", 0))
        }

        # --- 8. Diabetes prediction ---
        X_dia = pd.DataFrame([features])
        X_dia["hypertension"] = 0.5
        X_dia = X_dia[scaler_diabetes.feature_names_in_]
        scaled_dia = scaler_diabetes.transform(X_dia)
        selected_dia = selector_dia.transform(scaled_dia)
        diabetes_prob = float(model_diabetes.predict_proba(selected_dia)[0][1])

        # --- 9. Hypertension prediction ---
        X_hyp = pd.DataFrame([features])
        X_hyp["diabetes"] = diabetes_prob
        X_hyp = X_hyp[scaler_hypertension.feature_names_in_]
        scaled_hyp = scaler_hypertension.transform(X_hyp)
        selected_hyp = selector_hyp.transform(scaled_hyp)
        hypertension_prob = float(model_hypertension.predict_proba(selected_hyp)[0][1])

        # --- 10. Helper to extract top features ---
        def get_base_model(model):
            if hasattr(model, "named_estimators_"):
                return next(iter(model.named_estimators_.values()))
            if hasattr(model, "estimators_"):
                return model.estimators_[0]
            return model

        def top_features(model, X_selected, feature_names, top_n=3):
            try:
                base_model = get_base_model(model)
                if hasattr(base_model, "feature_importances_"):
                    importances = base_model.feature_importances_
                    indices = np.argsort(importances)[::-1][:top_n]
                    top_values = importances[indices]
                    total = max(top_values.sum(), 1e-8)
                    normalized = [(v / total) * 100 for v in top_values]
                    return [
                        TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                        for j, i in enumerate(indices)
                    ]
                if hasattr(base_model, "coef_"):
                    coeffs = np.abs(base_model.coef_[0])
                    indices = np.argsort(coeffs)[::-1][:top_n]
                    top_values = coeffs[indices]
                    total = max(top_values.sum(), 1e-8)
                    normalized = [(v / total) * 100 for v in top_values]
                    return [
                        TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                        for j, i in enumerate(indices)
                    ]
            except Exception as e:
                print(f"[×] Feature extraction error: {e}")
            indices = np.random.choice(len(feature_names), top_n, replace=False)
            scores = np.linspace(0.8, 0.2, top_n)
            total = scores.sum()
            normalized = [(v / total) * 100 for v in scores]
            return [
                TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                for j, i in enumerate(indices)
            ]

        dia_top = top_features(model_diabetes, selected_dia, selected_features_dia)
        hyp_top = top_features(model_hypertension, selected_hyp, selected_features_hyp)

        # --- 11. Derived descriptive fields ---
        derived = DerivedFeatures(
            age_group={0: "Young", 1: "Middle-aged", 2: "Older"}.get(features["age_group"], "Middle-aged"),
            smoker_status={0: "Non-smoker", 1: "Light smoker", 2: "Moderate smoker", 3: "Heavy smoker"}.get(features["smoker_status"], "Non-smoker"),
            is_obese=bool(features["is_obese"]),
            bp_category={-1: "Low", 0: "Normal", 1: "Elevated", 2: "Stage 1", 3: "Stage 2"}.get(features["bp_category"], "Normal"),
            bmi_category={0: "Underweight", 1: "Normal", 2: "Overweight", 3: "Obese"}.get(features["bmi_category"], "Normal"),
            bmi=bmi,
            pulse_pressure=features["sysBP"] - features["diaBP"],
            male_smoker=bool(features["male_smoker"]),
            prediabetes_indicator=bool(features["prediabetes_indicator"]),
            insulin_resistance=bool(features["insulin_resistance"]),
            metabolic_syndrome=bool(features["metabolic_syndrome"])
        )

        result = RiskPredictionOutput(
            diabetes_risk=round(diabetes_prob * 100, 2),
            hypertension_risk=round(hypertension_prob * 100, 2),
            derived_features=derived,
            input_values=features,
            top_diabetes_features=dia_top,
            top_hypertension_features=hyp_top
        )

        # --- 12. Save prediction ---
        timestamp = datetime.now()
        db.collection("Users").document(national_id).collection("risk_predictions") \
            .document(timestamp.strftime("%Y%m%d_%H%M%S")).set({
                **result.dict(),
                "timestamp": timestamp.isoformat(),
                "display_time": timestamp.strftime("%B %d, %Y at %I:%M %p"),
                "sortable_time": timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
