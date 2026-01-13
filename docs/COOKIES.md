# 🍪 Cookie Strategy Guide

Social media platforms increasingly block automated downloaders (like `yt-dlp`). To reliably download content from Twitter (X), Instagram, Facebook, and sometimes YouTube, you **must** provide cookies.

## 🎯 Which Platforms Need Cookies?

| Platform | Need Cookies? | Why? |
| :--- | :--- | :--- |
| **Twitter (X)** | **REQUIRED** 🔴 | API is strictly closed. Without cookies, almost all requests fail (400/403/500). |
| **Instagram** | **REQUIRED** 🔴 | Highly aggressive anti-bot protection. Login is mandatory. |
| **Facebook** | **REQUIRED** 🔴 | Most content (except very public reels) is behind login. |
| **YouTube** | Recommended 🟡 | Prevents throttling (slow downloads) and age-gated content blocks. |
| **TikTok** | Optional 🟢 | Usually works without cookies, but helps if you get Captchas. |

## 🛠️ How to Export Cookies

We use the **Netscape HTTP Cookie File** format (`cookies.txt`).

### Step 1: Install Browser Extension
Install **"Get cookies.txt LOCALLY"** (open source & safe):
- [Chrome / Edge / Brave Extension](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- [Firefox Extension](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)

### Step 2: Export from Browser
1. Log in to the target site (e.g., `twitter.com`) in your browser.
2. Click the extension icon.
3. Click **"Export All Cookies"** (or just for this domain).
4. Save the file.

## 📂 Where to Put Cookies

You need to place the files in the specific folders on your server.
*Note: Filename must end with `.txt` (e.g., `cookies.txt`).*

| Platform | Path on Server |
| :--- | :--- |
| Twitter | `cookies/twitter/cookies.txt` |
| Instagram | `cookies/instagram/cookies.txt` |
| Facebook | `cookies/facebook/cookies.txt` |
| YouTube | `cookies/youtube/cookies.txt` |
| TikTok | `cookies/tiktok/cookies.txt` |

## ⚠️ Security Warning

**NEVER share your `cookies.txt` files.** They contain your session tokens. Anyone with this file can log in as you.
- Do NOT commit them to GitHub.
- Do NOT share them in chat.

## 🔐 Fixing "Permission Denied"

If you cannot create these folders, it's because Docker (root) owns them. Fix it with:

```bash
# Unlock folders
sudo chown -R $USER:$USER cookies/ downloads/

# Create folders
mkdir -p cookies/twitter cookies/instagram cookies/facebook cookies/youtube cookies/tiktok
```
