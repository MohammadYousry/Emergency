from firebase_admin import credentials, firestore, initialize_app, _apps

# ✅ Initialize Firebase Admin SDK (only once, safely)
if not _apps:
    cred = credentials.Certificate("/etc/secrets/firebase_key.json")  # ← غيّر للمسار الصحيح
    initialize_app(cred)

# ✅ Firestore client
db = firestore.client()

# ✅ Loop through all users in the "Users" collection
users_ref = db.collection("Users").stream()

updated_count = 0

for doc in users_ref:
    national_id = doc.id
    print(f"🔄 Updating QR for {national_id}...")

    qr_ref = db.collection("Users").document(national_id).collection("QRCodeAccess").document("single_qr_code")

    # ✅ Set the public-facing web link to the emergency card page
    qr_ref.set({
        "qr_data": f"https://medigo-eg.netlify.app/card/emergency_card.html?user_id={national_id}",
        "image_url": f"https://medigo-eg.netlify.app/card/emergency_card.html?user_id={national_id}"  # optional: duplicate if frontend uses it
    }, merge=True)

    print(f"✅ Done for {national_id}")
    updated_count += 1

print(f"🎉 All QR links updated successfully for {updated_count} users.")
