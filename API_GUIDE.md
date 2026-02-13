# Media Downloader API - Kullanım Kılavuzu

Bu döküman, Media Downloader API'sinin nasıl kullanılacağını ve yapılandırılacağını açıklar.

---

## 📌 Genel Bakış

Media Downloader API, YouTube, Twitter, Instagram, TikTok, Facebook, Reddit ve diğer platformlardan medya indirmenizi sağlar. İndirilen dosyaların `creation_time` metadata'sı otomatik olarak güncel zaman damgasıyla güncellenir.

### Temel Özellikler
- **Asenkron İndirme**: Celery ile arka planda işlem
- **Metadata Manipülasyonu**: FFmpeg ile creation_time güncelleme
- **Güvenlik**: Firebase App Check, Rate Limiting, Spam Koruması
- **High Performance**: Nginx X-Accel-Redirect ile dosya sunumu

---

## 🌐 Erişim Noktaları

### Development Ortamı
| Servis | URL | Açıklama |
|--------|-----|----------|
| API (Nginx üzerinden) | `http://localhost:8090` | Frontend buraya istek atar |
| API Docs (Scalar) | `http://localhost:8090/scalar` | Modern API dökümantasyonu |
| API Docs (Swagger) | `http://localhost:8090/docs` | Klasik Swagger UI |
| API (Direkt - Sadece Debug) | `http://127.0.0.1:8001` | Sadece localhost'tan erişilebilir |

### Production Ortamı
| Servis | URL | Açıklama |
|--------|-----|----------|
| API (Nginx üzerinden) | `https://api.yourdomain.com` | SSL ile korumalı |
| API Docs | `https://api.yourdomain.com/scalar` | Scalar UI |

> ⚠️ **Önemli**: Production'da API direkt erişime kapalıdır. Tüm trafik Nginx üzerinden geçer.

---

## 🔐 Kimlik Doğrulama

Kimlik doğrulama davranışı yapılandırılabilir:

- `X-App-Secret`: `APP_SECRET_KEY` ile eşleşirse VIP bypass aktif olur.
- `X-Firebase-AppCheck`: Sadece `REQUIRE_FIREBASE_APPCHECK=true` ise ve istek VIP değilse zorunludur.

### Örnek Header'lar
```http
X-App-Secret: <APP_SECRET_KEY>
X-Firebase-AppCheck: <valid_token>
```

> Not: VIP header artık Nginx üzerinden geçen isteklerde de backend'e iletilir.

---

## 📡 API Endpoints

### 1. Health Check
```http
GET /
```
**Response:**
```json
{
  "success": true,
  "code": "API_READY",
  "status_code": 200,
  "message": "Media Downloader API is running."
}
```

---

### 2. İndirme Başlat
```http
POST /download
Content-Type: application/json

{
  "url": "https://www.youtube.com/shorts/vNxl7L3Zuck"
}
```
**Response (202 Accepted):**
```json
{
  "success": true,
  "code": "DOWNLOAD_STARTED",
  "status_code": 202,
  "data": {
    "task_id": "abc123-def456-...",
    "estimated_size_mb": 12.3
  }
}
```

---

### 3. İndirme Durumu Sorgula
```http
GET /status/{task_id}
```
**Response (In Progress):**
```json
{
  "success": true,
  "code": "TASK_IN_PROGRESS",
  "status_code": 200,
  "data": {
    "task_id": "abc123-def456-...",
    "status": "STARTED"
  }
}
```

**Response (Completed):**
```json
{
  "success": true,
  "code": "TASK_COMPLETED",
  "status_code": 200,
  "data": {
    "task_id": "abc123-def456-...",
    "status": "SUCCESS",
    "data": {
      "file_path": "/app/downloads/video.mp4",
      "filename": "video.mp4"
    }
  }
}
```

---

### 4. Dosya İndir
```http
GET /files/{task_id}
```
**Response:** Binary dosya (video/mp4, image/jpeg, vb.)

> Not: Dosya Nginx tarafından `X-Accel-Redirect` ile sunulur.

---

## ⚡ Rate Limiting

| Limit | Değer |
|-------|-------|
| İstek/Saat | 180 |
| MB/Saat | 250 MB |
| Dosya Başına | 50 MB |
| Spam Ban Süresi | 5 dakika |

---

## 🚨 Hata Kodları

| Kod | HTTP | Açıklama |
|-----|------|----------|
| `API_READY` | 200 | API çalışıyor |
| `DOWNLOAD_STARTED` | 202 | İndirme başlatıldı |
| `TASK_IN_PROGRESS` | 200 | Görev hâlâ çalışıyor |
| `TASK_COMPLETED` | 200 | Görev tamamlandı |
| `TASK_FAILED` | 200 (payload status_code=500) | Worker görevi başarısız oldu |
| `INVALID_URL` | 400 | URL geçersiz veya eksik |
| `INVALID_TOKEN` | 401 | App Check token eksik/geçersiz |
| `FILE_NOT_READY` | 404 | Dosya henüz hazır değil |
| `FILE_NOT_FOUND` | 404 | Dosya bulunamadı |
| `FILE_TOO_LARGE` | 413 | Dosya boyutu sınırı aşıldı (>50MB) |
| `TOO_MANY_REQUESTS` | 429 | Rate limit aşıldı |
| `VOLUME_LIMIT_EXCEEDED` | 429 | Saatlik veri limiti aşıldı |
| `SPAM_DETECTED` | 429 | Spam tespit edildi, geçici ban |
| `SERVICE_UNAVAILABLE` | 503 | App Check zorunlu ama sunucuda yapılandırma eksik |
| `INTERNAL_ERROR` | 500 | Sunucu hatası |

---

## 🐳 Docker ile Çalıştırma

### Development
```bash
# .env dosyasını oluştur
cp .env.example .env

# Servisleri başlat
docker compose up --build -d

# Logları izle
docker compose logs -f api
```

### Production
```bash
# .env dosyasında ENV=production yap
# Firebase credentials'ı yapılandır
docker compose -f docker-compose.prod.yml up -d
```

---

## 🧪 Test

```bash
# Redis'i temizle
docker exec downloader_redis redis-cli FLUSHALL

# Testleri çalıştır
pytest tests/integration_test.py -v
```

---

## � Frontend Akışı (Orchestration)

Frontend'in API'yi nasıl kullanması gerektiğini gösteren tam akış:

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND AKIŞ DİYAGRAMI                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Kullanıcı URL'i girer                                   │
│            │                                                │
│            ▼                                                │
│  2. POST /download { url: "..." }                           │
│            │                                                │
│            ├──▶ 202 Accepted ──▶ task_id al                 │
│            │                          │                     │
│            │                          ▼                     │
│            │              3. Polling başlat                 │
│            │                          │                     │
│            │                          ▼                     │
│            │              GET /status/{task_id}             │
│            │                          │                     │
│            │         ┌────────────────┼────────────────┐    │
│            │         │                │                │    │
│            │         ▼                ▼                ▼    │
│            │     PENDING          PROGRESS         SUCCESS  │
│            │         │                │                │    │
│            │         └───────┬────────┘                │    │
│            │                 │                         │    │
│            │           2sn bekle                       │    │
│            │                 │                         │    │
│            │                 ▼                         │    │
│            │         Tekrar sorgula                    │    │
│            │                                           │    │
│            │                                           ▼    │
│            │                              4. GET /files/{task_id} │
│            │                                           │    │
│            │                                           ▼    │
│            │                               Dosyayı kaydet   │
│            │                                                │
│            ├──▶ 400 Bad Request ──▶ Hata göster             │
│            ├──▶ 429 Too Many ──▶ Rate limit uyarısı         │
│            └──▶ 500 Error ──▶ Tekrar dene veya hata göster  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### React Native / TypeScript Örnek Kodu

```typescript
// types.ts
interface ApiResponse<T> {
  success: boolean;
  code: string;
  status_code: number;
  message?: string;
  data?: T;
}

interface DownloadStartResponse {
  task_id: string;
}

interface TaskStatusResponse {
  task_id: string;
  status: 'PENDING' | 'STARTED' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  file_path?: string;
  filename?: string;
}

// api.ts
const API_BASE = __DEV__ 
  ? 'http://localhost:8090'  // Development
  : 'https://api.yourdomain.com';  // Production

const headers = {
  'Content-Type': 'application/json',
  // Development bypass (remove in production)
  ...__DEV__ && { 'X-App-Secret': 'dev_secret_bypass' },
  // If REQUIRE_FIREBASE_APPCHECK=true, add Firebase App Check token
  // 'X-Firebase-AppCheck': await firebase.appCheck().getToken().then(res => res.token),
};

async function downloadMedia(url: string): Promise<string> {
  // 1. Start download
  const startRes = await fetch(`${API_BASE}/download`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ url }),
  });
  
  const startData: ApiResponse<DownloadStartResponse> = await startRes.json();
  
  if (!startData.success) {
    throw new Error(startData.message || startData.code);
  }
  
  const taskId = startData.data!.task_id;
  
  // 2. Poll for status
  let status: TaskStatusResponse;
  do {
    await new Promise(resolve => setTimeout(resolve, 2000)); // 2 second delay
    
    const statusRes = await fetch(`${API_BASE}/status/${taskId}`);
    const statusData: ApiResponse<TaskStatusResponse> = await statusRes.json();
    status = statusData.data!;
    
  } while (status.status !== 'SUCCESS' && status.status !== 'FAILURE');
  
  if (status.status === 'FAILURE') {
    throw new Error('Download failed on server');
  }
  
  // 3. Download file
  const fileUrl = `${API_BASE}/files/${taskId}`;
  return fileUrl; // Return URL for download/display
}

// Usage
try {
  const fileUrl = await downloadMedia('https://www.youtube.com/shorts/abc123');
  // Use fileUrl to save or display the file
} catch (error) {
  console.error('Download error:', error.message);
}
```

### Polling Stratejisi

| Durum | Aralık | Maksimum Deneme |
|-------|--------|-----------------|
| İlk 30 saniye | 2 saniye | 15 |
| 30-60 saniye | 3 saniye | 10 |
| 60+ saniye | 5 saniye | 20 |

> **İpucu**: Çok uzun süren indirmeler için kullanıcıya bildirim göster ve arka planda polling yap.

---

## �📊 Mimari

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│    Nginx    │────▶│   FastAPI   │
│  (Expo App) │     │   (Proxy)   │     │    (API)    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  Downloads  │     │   Celery    │
                    │   (Files)   │     │  (Worker)   │
                    └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Valkey    │
                                        │   (Redis)   │
                                        └─────────────┘
```
