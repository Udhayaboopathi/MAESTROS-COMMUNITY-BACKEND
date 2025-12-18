"""
Test script to verify CORS configuration
Run this on your server after deploying the changes
"""

import requests

# Test the API endpoint with CORS headers
def test_cors():
    url = "http://4.186.28.20/discord/stats"
    origin = "http://localhost:3000"
    
    print(f"Testing CORS for {url} from origin {origin}\n")
    
    # Test OPTIONS preflight request
    print("1. Testing OPTIONS (preflight) request...")
    try:
        response = requests.options(
            url,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type"
            }
        )
        print(f"   Status: {response.status_code}")
        print(f"   Access-Control-Allow-Origin: {response.headers.get('Access-Control-Allow-Origin', 'NOT SET')}")
        print(f"   Access-Control-Allow-Methods: {response.headers.get('Access-Control-Allow-Methods', 'NOT SET')}")
        print(f"   Access-Control-Allow-Credentials: {response.headers.get('Access-Control-Allow-Credentials', 'NOT SET')}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print()
    
    # Test actual GET request
    print("2. Testing GET request...")
    try:
        response = requests.get(
            url,
            headers={
                "Origin": origin
            }
        )
        print(f"   Status: {response.status_code}")
        print(f"   Access-Control-Allow-Origin: {response.headers.get('Access-Control-Allow-Origin', 'NOT SET')}")
        print(f"   Access-Control-Allow-Credentials: {response.headers.get('Access-Control-Allow-Credentials', 'NOT SET')}")
        if response.status_code == 200:
            print(f"   ✅ SUCCESS - CORS headers present")
        else:
            print(f"   ⚠️  Response: {response.text[:200]}")
    except Exception as e:
        print(f"   ERROR: {e}")

if __name__ == "__main__":
    test_cors()
