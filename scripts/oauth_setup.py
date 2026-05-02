#!/usr/bin/env python3
"""
oauth_setup.py — Workaround para el bug de Personal Access Tokens en pixelfed.social
(https://github.com/pixelfed/pixelfed/issues/6502).

Registra una app via /api/v1/apps (Mastodon-compatible), abre la URL de autorización
en tu navegador, te pide pegar el código de autorización que Pixelfed muestra, lo canjea
por un access token y lo guarda en ~/.config/hispania-obscura/.env (chmod 600).

Uso:
    python3 oauth_setup.py
    # opcional:
    python3 oauth_setup.py --instance pixelfed.social --scopes "read write"

Requiere: stdlib only (urllib + json). Cero dependencias.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_INSTANCE = "pixelfed.social"
DEFAULT_SCOPES = "read write"
DEFAULT_APP_NAME = "hispania-obscura-alttext"
DEFAULT_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"  # out-of-band → Pixelfed muestra el code en el browser
DEFAULT_WEBSITE = "https://impermanente.es"
ENV_PATH = Path.home() / ".config" / "hispania-obscura" / ".env"


def http_post(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urlencode(data).encode()
    req = Request(url, data=body, method="POST", headers=headers or {})
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except HTTPError as e:
        raw = e.read().decode(errors="replace")
        print(f"\n❌ HTTP {e.code} en {url}")
        print(raw)
        sys.exit(1)
    except URLError as e:
        print(f"\n❌ Error de red: {e}")
        sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"\n❌ Respuesta no-JSON de {url}:\n{raw[:500]}")
        sys.exit(1)


def http_get(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers=headers or {})
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        raw = e.read().decode(errors="replace")
        print(f"\n❌ HTTP {e.code} en {url}\n{raw}")
        sys.exit(1)


def write_env(values: dict) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            existing[k.strip()] = v.strip().strip('"').strip("'")
    existing.update(values)
    body = "\n".join(f'{k}="{v}"' for k, v in existing.items()) + "\n"
    ENV_PATH.write_text(body)
    os.chmod(ENV_PATH, 0o600)


def main() -> None:
    p = argparse.ArgumentParser(description="OAuth setup para Pixelfed (workaround bug #6502).")
    p.add_argument("--instance", default=DEFAULT_INSTANCE, help="Hostname del instance (sin https://).")
    p.add_argument("--scopes", default=DEFAULT_SCOPES, help='Scopes separados por espacio. Ej: "read write".')
    p.add_argument("--app-name", default=DEFAULT_APP_NAME)
    p.add_argument("--redirect", default=DEFAULT_REDIRECT)
    p.add_argument("--website", default=DEFAULT_WEBSITE)
    p.add_argument("--no-browser", action="store_true", help="No abrir el navegador automáticamente.")
    args = p.parse_args()

    base = f"https://{args.instance}"

    print("=" * 70)
    print(f"OAuth setup para {args.instance}")
    print(f"App: {args.app_name}")
    print(f"Scopes: {args.scopes}")
    print("=" * 70)

    # Paso 1: registrar la app
    print("\n[1/3] Registrando app via /api/v1/apps …")
    app = http_post(
        f"{base}/api/v1/apps",
        {
            "client_name": args.app_name,
            "redirect_uris": args.redirect,
            "scopes": args.scopes,
            "website": args.website,
        },
    )
    if "client_id" not in app or "client_secret" not in app:
        print(f"❌ Respuesta inesperada: {app}")
        sys.exit(1)
    client_id = app["client_id"]
    client_secret = app["client_secret"]
    print(f"   ✅ client_id obtenido (longitud {len(client_id)})")

    # Paso 2: autorización interactiva
    auth_qs = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": args.redirect,
            "scope": args.scopes,
            "response_type": "code",
        }
    )
    auth_url = f"{base}/oauth/authorize?{auth_qs}"

    print(f"\n[2/3] Abre esta URL en tu navegador (sesión iniciada en {args.instance}):\n")
    print(f"   {auth_url}\n")
    print("   Pixelfed te pedirá confirmar el acceso.")
    print(f"   Después mostrará un código de autorización en pantalla.")
    print("   Cópialo y pégalo aquí.\n")

    if not args.no_browser:
        try:
            webbrowser.open(auth_url, new=2)
            print("   (intentando abrir el navegador automáticamente…)\n")
        except Exception:
            pass

    code = input("Pega aquí el código de autorización: ").strip()
    if not code:
        print("❌ Código vacío. Abortando.")
        sys.exit(1)

    # Paso 3: canjear code por access_token
    print("\n[3/3] Canjeando código por access_token …")
    token_resp = http_post(
        f"{base}/oauth/token",
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": args.redirect,
            "code": code,
            "scope": args.scopes,
        },
    )
    if "access_token" not in token_resp:
        print(f"❌ Respuesta inesperada: {token_resp}")
        sys.exit(1)
    access_token = token_resp["access_token"]
    print(f"   ✅ access_token obtenido (longitud {len(access_token)})")

    # Verificación: leer credenciales con el token
    print("\nVerificando con /api/v1/accounts/verify_credentials …")
    me = http_get(
        f"{base}/api/v1/accounts/verify_credentials",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    print(f"   ✅ Autenticado como @{me.get('username')} (id={me.get('id')})")

    # Guardar
    write_env(
        {
            "PIXELFED_INSTANCE": args.instance,
            "PIXELFED_CLIENT_ID": client_id,
            "PIXELFED_CLIENT_SECRET": client_secret,
            "PIXELFED_ACCESS_TOKEN": access_token,
            "PIXELFED_USERNAME": me.get("username", ""),
            "PIXELFED_ACCOUNT_ID": str(me.get("id", "")),
            "PIXELFED_SCOPES": args.scopes,
        }
    )
    print(f"\n✅ Credenciales guardadas en {ENV_PATH} (chmod 600)")
    print(
        "\nPara usarlo:\n"
        f"   set -a; source {ENV_PATH}; set +a\n"
        '   curl -H "Authorization: Bearer $PIXELFED_ACCESS_TOKEN" \\\n'
        '        https://$PIXELFED_INSTANCE/api/v1/accounts/verify_credentials\n'
    )


if __name__ == "__main__":
    main()
