#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카카오 OAuth 토큰 발급 및 .env 자동 업데이트 스크립트
"""

import io
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

# 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ENV_PATH = Path(__file__).resolve().parent / ".env"

def load_env(env_file: Path) -> dict:
    env_vars = {}
    if not env_file.exists():
        return env_vars
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars

def save_env_var(env_file: Path, key: str, value: str):
    lines = []
    found = False
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def issue_token(code: str, redirect_uri: str = "http://localhost"):
    env_vars = load_env(ENV_PATH)
    client_id = env_vars.get("KAKAO_REST_API_KEY")
    client_secret = env_vars.get("KAKAO_CLIENT_SECRET")

    if not client_id:
        print("[오류] .env 파일에 KAKAO_REST_API_KEY가 존재하지 않습니다.")
        sys.exit(1)

    url = "https://kauth.kakao.com/oauth/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code.strip(),
    }
    if client_secret:
        params["client_secret"] = client_secret

    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            token_data = json.loads(body)
            
            refresh_token = token_data.get("refresh_token")
            access_token = token_data.get("access_token")

            if not refresh_token:
                print("[오류] 카카오 응답에 refresh_token이 포함되어 있지 않습니다:")
                print(json.dumps(token_data, indent=2, ensure_ascii=False))
                sys.exit(1)

            # .env 파일에 저장
            save_env_var(ENV_PATH, "KAKAO_REDIRECT_URI", redirect_uri)
            save_env_var(ENV_PATH, "KAKAO_REFRESH_TOKEN", refresh_token)
            if access_token:
                save_env_var(ENV_PATH, "KAKAO_ACCESS_TOKEN", access_token)

            print("=" * 60)
            print("[성공] 카카오 토큰 발급 완료!")
            print(f"Refresh Token: {refresh_token[:15]}... (저장 완료)")
            print(f"Access Token : {access_token[:15]}... (저장 완료)")
            print(f".env 파일에 KAKAO_REFRESH_TOKEN 저장이 완료되었습니다.")
            print("=" * 60)
            return token_data

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[카카오 API 오류 HTTP {e.code}]")
        try:
            err_json = json.loads(err_msg)
            print(f"   에러 코드: {err_json.get('error_code')}")
            print(f"   에러 설명: {err_json.get('error_description')}")
        except Exception:
            print(f"   {err_msg}")
        return None
    except Exception as e:
        print(f"[요청 실패]: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        auth_code = sys.argv[1]
        uri = sys.argv[2] if len(sys.argv) > 2 else "http://localhost"
        issue_token(auth_code, uri)
    else:
        print("사용법: python get_kakao_token.py <인가코드> [redirect_uri]")
