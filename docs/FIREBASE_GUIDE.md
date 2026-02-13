# Firebase App Check Setup Guide

This backend can enforce **Firebase App Check** for non-VIP requests. Enforcement is controlled by environment configuration.

## 1. Get the Service Account Key

You need a Firebase service account JSON file so the backend can verify App Check tokens.

1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Open **Project settings**.
3. Open the **Service accounts** tab.
4. Click **Generate new private key**.
5. Save the downloaded JSON file.

## 2. Install the File

1. Rename the downloaded file to `firebase-auth.json`.
2. Move it to the root of this project.
3. Ensure `.env` contains:

```env
FIREBASE_SERVICE_ACCOUNT_JSON=/app/firebase-auth.json
```

## 3. Choose Enforcement Mode

Set this in `.env`:

```env
REQUIRE_FIREBASE_APPCHECK=true
```

- `true`: non-VIP requests must include valid `X-Firebase-AppCheck`.
- `false`: App Check is not required.

VIP requests (`X-App-Secret` matches `APP_SECRET_KEY`) bypass App Check checks.

## 4. Restart Services

```bash
docker compose down && docker compose up -d
```

## 5. Runtime Behavior Summary

- `REQUIRE_FIREBASE_APPCHECK=false`: App Check is skipped for regular users and VIP users.
- `REQUIRE_FIREBASE_APPCHECK=true` + valid Firebase file: non-VIP requires valid token.
- `REQUIRE_FIREBASE_APPCHECK=true` + missing/invalid Firebase file: non-VIP receives `503 SERVICE_UNAVAILABLE`.

## 6. Client Header

When App Check is enabled for non-VIP clients, the mobile app must send:

```http
X-Firebase-AppCheck: <valid_token>
```
