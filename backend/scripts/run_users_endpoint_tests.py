"""Run basic checks for user endpoints without pytest dependency.

This script uses FastAPI TestClient to call endpoints and assert expected responses.
"""
import sys
from fastapi.testclient import TestClient

try:
    from backend.main import app
except Exception as e:
    print("Failed to import app:", e)
    sys.exit(2)

client = TestClient(app)

failed = False

print('Testing PUT /api/users/{id}/display-name (unauthenticated)')
resp = client.put('/api/users/some-id/display-name', json={'display_name': 'NewName'})
print('Status code:', resp.status_code)
if resp.status_code != 401:
    print('Expected 401 for unauthenticated; got', resp.status_code)
    failed = True

print('Testing PUT /api/users/{id}/email-settings (unauthenticated)')
resp = client.put('/api/users/some-id/email-settings', json={'email_on_new_question': True})
print('Status code:', resp.status_code)
if resp.status_code != 401:
    print('Expected 401 for unauthenticated; got', resp.status_code)
    failed = True

print('Testing PUT /api/users/{id}/push-settings (unauthenticated)')
resp = client.put('/api/users/some-id/push-settings', json={'push_notifications_enabled': True})
print('Status code:', resp.status_code)
if resp.status_code != 401:
    print('Expected 401 for unauthenticated; got', resp.status_code)
    failed = True

print('Testing GET /api/users/{id}/settings (unauthenticated)')
resp = client.get('/api/users/some-id/settings')
print('Status code:', resp.status_code)
if resp.status_code != 401:
    print('Expected 401 for unauthenticated; got', resp.status_code)
    failed = True

if failed:
    print('\nOne or more tests failed')
    sys.exit(1)
print('\nAll simple endpoint tests passed (unauthenticated returns 401)')
