"""Google service-account auth with the standard library + the openssl CLI only
(no pip installs). Shared by refresh_data.py (Sheets) and enrich_gsc.py (Search
Console).
"""
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_URI = 'https://oauth2.googleapis.com/token'


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def load_sa(key_path: str) -> dict:
    try:
        sa = json.loads(Path(key_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f'Could not read service-account key {key_path}: {e}')
    for field in ('client_email', 'private_key'):
        if field not in sa:
            sys.exit(f'{key_path} is missing "{field}" — is this a service-account key JSON?')
    return sa


def sign_jwt(sa: dict, scope: str) -> str:
    """Build and RS256-sign a service-account JWT using the openssl CLI."""
    now = int(time.time())
    header = {'alg': 'RS256', 'typ': 'JWT'}
    claims = {
        'iss': sa['client_email'],
        'scope': scope,
        'aud': sa.get('token_uri', TOKEN_URI),
        'iat': now,
        'exp': now + 3600,
    }
    signing_input = (_b64url(json.dumps(header).encode()) + '.' +
                     _b64url(json.dumps(claims).encode()))
    with tempfile.NamedTemporaryFile('w', suffix='.pem') as key_file:
        key_file.write(sa['private_key'])
        key_file.flush()
        try:
            proc = subprocess.run(
                ['openssl', 'dgst', '-sha256', '-sign', key_file.name],
                input=signing_input.encode('ascii'),
                capture_output=True, check=True)
        except FileNotFoundError:
            sys.exit('openssl not found — install OpenSSL to use service-account auth.')
        except subprocess.CalledProcessError as e:
            sys.exit(f'openssl failed to sign the JWT: {e.stderr.decode().strip()}')
    return signing_input + '.' + _b64url(proc.stdout)


def get_access_token(sa: dict, scope: str) -> str:
    """Exchange a signed JWT for an OAuth2 access token for the given scope."""
    token_uri = sa.get('token_uri', TOKEN_URI)
    assertion = sign_jwt(sa, scope)
    body = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion,
    }).encode('ascii')
    req = urllib.request.Request(token_uri, data=body, method='POST',
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)['access_token']
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        sys.exit(f'Token exchange failed ({e.code}): {detail}\n'
                 'Check that the key file is a valid, non-revoked service-account key.')
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f'Could not reach {token_uri}: {getattr(e, "reason", e)} — '
                 'check your internet connection.')
