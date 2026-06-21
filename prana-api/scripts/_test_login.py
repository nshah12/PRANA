import urllib.request, json

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

code, body = post('http://localhost:8000/auth/admin/login', {'email': 'admin@prana.in', 'password': 'Prana@Admin0124'})
print(f'PA login: {code}', body)

code2, body2 = post('http://localhost:8000/auth/org/login', {'email': 'admin@techcorp.in', 'password': 'Prana@Admin0124'})
print(f'OA login: {code2}', body2)
