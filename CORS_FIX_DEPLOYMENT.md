# CORS Fix Deployment Guide

## Changes Made

### 1. Updated `backend/main.py`

- ✅ CORS middleware now explicitly includes all required origins
- ✅ Middleware is added BEFORE routers (critical for proper CORS handling)
- ✅ Added `expose_headers=["*"]` to ensure response headers are visible to browser
- ✅ Hardcoded essential origins: localhost:3000, 127.0.0.1:3000, 4.186.28.20

### 2. Updated `backend/.env.production`

- ✅ Added localhost and public IP origins to CORS_ORIGINS

### 3. Created `backend/nginx.conf` (if using Nginx)

- ✅ Prevents double CORS headers
- ✅ Lets FastAPI handle all CORS
- ✅ Properly handles OPTIONS preflight requests

---

## Deployment Steps

### On Your Production Server (4.186.28.20):

#### Step 1: Pull/Upload Changes

```bash
# Navigate to your project directory
cd /path/to/MAESTROS_COMMUNITY/backend

# Pull changes if using git
git pull

# Or manually upload the modified files:
# - main.py
# - .env.production
# - nginx.conf (if using Nginx)
```

#### Step 2: Restart FastAPI Application

```bash
# If using systemd service
sudo systemctl restart maestros-api

# Or if running with screen/tmux
# Kill the old process and restart:
pkill -f "uvicorn main:app"
uvicorn main:app --host 0.0.0.0 --port 8000

# Or if using production WSGI server
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### Step 3: Update Nginx (if applicable)

```bash
# Copy nginx.conf to Nginx sites directory
sudo cp nginx.conf /etc/nginx/sites-available/maestros-api

# Create symlink if doesn't exist
sudo ln -s /etc/nginx/sites-available/maestros-api /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## Verification

### 1. Test from Command Line

```bash
# Test OPTIONS preflight
curl -X OPTIONS http://4.186.28.20/discord/stats \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -v

# Should see: Access-Control-Allow-Origin: http://localhost:3000

# Test GET request
curl -X GET http://4.186.28.20/discord/stats \
  -H "Origin: http://localhost:3000" \
  -v

# Should see: Access-Control-Allow-Origin: http://localhost:3000
```

### 2. Test from Browser Console

Open browser console on http://localhost:3000 and run:

```javascript
// Test fetch
fetch("http://4.186.28.20/discord/stats", {
  method: "GET",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
  },
})
  .then((r) => r.json())
  .then((data) => console.log("✅ SUCCESS:", data))
  .catch((err) => console.error("❌ FAILED:", err));
```

### 3. Check Browser Network Tab

- Open DevTools → Network tab
- Make a request to the API
- Check Response Headers should show:
  ```
  Access-Control-Allow-Origin: http://localhost:3000
  Access-Control-Allow-Credentials: true
  ```

---

## Troubleshooting

### Still Getting CORS Errors?

#### 1. Check FastAPI is Running

```bash
curl http://4.186.28.20/health
# Should return: {"status":"healthy",...}
```

#### 2. Check Which Port FastAPI is Using

```bash
# Find FastAPI process
ps aux | grep uvicorn
netstat -tlnp | grep :8000
```

#### 3. Check Nginx is Proxying Correctly

```bash
# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

#### 4. Verify Environment Variables Loaded

Add this temporary endpoint to main.py to check:

```python
@app.get("/debug/cors")
async def debug_cors():
    return {
        "configured_origins": allowed_origins,
        "from_settings": settings.cors_origins_list
    }
```

#### 5. Check Firewall Rules

```bash
# Ensure port 80 (or 8000) is open
sudo ufw status
sudo iptables -L
```

### Common Issues:

**❌ "ERR_CONNECTION_REFUSED"**

- FastAPI not running or wrong port
- Firewall blocking connections

**❌ "No Access-Control-Allow-Origin header"**

- CORS middleware not configured (fixed in this update)
- Nginx stripping headers (fixed in nginx.conf)

**❌ "403 Forbidden"**

- Check Nginx permissions
- Check FastAPI is accessible on localhost:8000

**❌ OPTIONS returns 404**

- FastAPI should handle OPTIONS automatically
- Check Nginx isn't blocking OPTIONS (fixed in nginx.conf)

---

## Expected Result

✅ Browser console: No CORS errors
✅ Network tab: Shows `Access-Control-Allow-Origin` header
✅ API calls succeed from http://localhost:3000
✅ `/discord/stats` returns data
✅ `/discord/guild/members` returns data

---

## Testing Script

Run the provided test script on your server:

```bash
python test_cors.py
```

This will verify CORS configuration without needing a browser.
