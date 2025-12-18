#!/usr/bin/env python3
"""
Quick Backend Health Check
Tests if your backend is accessible and CORS is configured
"""

import requests
import sys
from typing import Dict

def test_endpoint(url: str, origin: str) -> Dict:
    """Test a single endpoint with CORS headers"""
    try:
        # Test OPTIONS (preflight)
        options_response = requests.options(
            url,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=5
        )
        
        # Test GET
        get_response = requests.get(
            url,
            headers={"Origin": origin},
            timeout=5
        )
        
        return {
            "success": get_response.status_code == 200,
            "status": get_response.status_code,
            "cors_header": get_response.headers.get('Access-Control-Allow-Origin', 'NOT SET'),
            "options_status": options_response.status_code,
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "CONNECTION_REFUSED - Backend not running or not accessible"
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "TIMEOUT - Backend took too long to respond"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main():
    backend_url = "http://4.186.28.20"
    origin = "http://localhost:3000"
    
    print("=" * 60)
    print("🔍 MAESTROS COMMUNITY - Backend Health Check")
    print("=" * 60)
    print(f"Backend URL: {backend_url}")
    print(f"Testing from origin: {origin}")
    print()
    
    endpoints = [
        "/health",
        "/discord/stats",
        "/",
    ]
    
    all_passed = True
    
    for endpoint in endpoints:
        full_url = f"{backend_url}{endpoint}"
        print(f"Testing: {endpoint}")
        print("-" * 60)
        
        result = test_endpoint(full_url, origin)
        
        if result.get("success"):
            print(f"✅ Status: {result['status']}")
            print(f"✅ CORS Header: {result['cors_header']}")
            print(f"✅ OPTIONS Status: {result['options_status']}")
        else:
            all_passed = False
            print(f"❌ FAILED")
            if "error" in result:
                print(f"   Error: {result['error']}")
            else:
                print(f"   Status: {result.get('status', 'UNKNOWN')}")
                print(f"   CORS Header: {result.get('cors_header', 'NOT SET')}")
        
        print()
    
    print("=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - CORS is configured correctly!")
        print("✅ Your React app should work without CORS errors")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print("\nTroubleshooting:")
        print("1. Is FastAPI backend running?")
        print("   → sudo systemctl status maestros-api")
        print("2. Is it listening on port 8000?")
        print("   → netstat -tlnp | grep :8000")
        print("3. Is firewall blocking connections?")
        print("   → sudo ufw status")
        sys.exit(1)

if __name__ == "__main__":
    main()
