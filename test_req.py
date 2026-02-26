import requests

url = "http://localhost:11434/v1/chat/completions"
data = {"model": "doesnotexist:123", "messages": [{"role": "user", "content": "Hello"}]}
resp = requests.post(url, json=data)
print("BODY:")
print(resp.text)
