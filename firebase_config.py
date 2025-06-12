import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ✅ تهيئة Firebase باستخدام متغير بيئي
if not firebase_admin._apps:
    firebase_key_json = os.environ.get("FIREBASE_KEY_JSON")
    if not firebase_key_json:
        raise ValueError("FIREBASE_KEY_JSON environment variable not set.")
    
    firebase_key_dict = json.loads(firebase_key_json)
    cred = credentials.Certificate(firebase_key_dict)
    
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'medi-go-eb65e.appspot.com'
    })

db = firestore.client()
bucket = storage.bucket()
