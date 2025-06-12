# firebase_config.py

import firebase_admin
from firebase_admin import credentials, firestore, storage

# ✅ تهيئة Firebase مرة واحدة فقط
if not firebase_admin._apps:
    cred = credentials.Certificate("/etc/secrets/firebase_key.json")  # غيّر للمسار الصحيح
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'medi-go-eb65e.firebasestorage.app'
    })

# ✅ العملاء الجاهزين
db = firestore.client()
bucket = storage.bucket()
