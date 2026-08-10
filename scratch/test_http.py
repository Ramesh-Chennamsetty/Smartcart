import urllib.request
import urllib.error

try:
    response = urllib.request.urlopen('http://127.0.0.1:5000/')
    print("Status:", response.status)
    with open('scratch/error.html', 'w', encoding='utf-8') as f:
        f.write(response.read().decode())
    print("Saved response to scratch/error.html")
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code)
    with open('scratch/error.html', 'w', encoding='utf-8') as f:
        f.write(e.read().decode())
    print("Saved error response to scratch/error.html")
except Exception as e:
    print("Error:", e)
