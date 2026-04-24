"""test_upload.py — Test upload endpoint locally"""
import requests

url = "http://localhost:8000/upload"

# Thử upload 1 file test nhỏ
test_file = "config/template_config.json"  # tạm thay bằng file json

try:
    with open(test_file, "rb") as f:
        files = {"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(url, files=files, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Headers: {dict(r.headers)}")
    print(f"Body: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
