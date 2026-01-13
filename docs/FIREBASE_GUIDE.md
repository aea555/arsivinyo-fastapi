# Firebase App Check Setup Guide

Your backend is already configured to use **Firebase App Check** to prevent abuse. This ensures that only requests coming from your authentic app (signed by Apple/Google) are accepted.

## 1. Get the Service Account Key

You need a generic "Service Account" JSON file that grants your backend "Admin" access to your Firebase project.

1.  Go to the **[Firebase Console](https://console.firebase.google.com/)**.
2.  Click the **Gear Icon ⚙️** next to checking "Project Overview" -> **Project settings**.
3.  Go to the **Service accounts** tab.
4.  Click **Generate new private key**.
5.  Click **Generate key**.
6.  This will download a `.json` file to your computer.

## 2. Install the File

1.  Rename the downloaded file to: `firebase-auth.json`
2.  Move it to the root folder of this project.

## 3. Enable Protection (Production Mode)

Once the file is in place, you can enforce security by switching to production mode.

1.  Open `.env` file.
2.  Change `ENV=development` to `ENV=production`.
3.  Restart containers:
    ```bash
    docker compose down && docker compose up -d
    ```

**What happens next?**
-   **If File Missing + Production:** The API will log a warning and block requests (or fail securely).
-   **If File Present + Production:** The API will verify the `X-Firebase-AppCheck` header on every request. Requests without a valid token will receive `401 Unauthorized`.

> [!IMPORTANT]  
> Make sure your mobile app sends the `X-Firebase-AppCheck` header! You need to implement App Check in your React Native / Expo app using `@react-native-firebase/app-check`.
