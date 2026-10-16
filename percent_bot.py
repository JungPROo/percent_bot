#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
percent_bot - 네이버 쇼핑 검색 기반 최저가 탐지 봇
- 검색 대상: '아이폰 13미니'
- 배송비 포함 실구매가 기준 저렴한 순서 5개 상품 정렬 및 출력
- 광고 상품 제거 및 진짜 상품 필터링
- 1위 가격의 목표가(300,000원) 도달 여부 점검 및 알림
- 값 수집 실패 시 임의 생성 없이 원인 출력 후 즉시 종료
"""

import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

# Windows 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ENV_PATH = Path(__file__).resolve().parent / ".env"

# 1. 설정값
KEYWORD = "아이폰 13미니"
TARGET_PRICE = 300000       # 목표가 300,000원
SORT_METHOD = "price_asc"
LIMIT = 20
TOP_COUNT = 5               # 출력 상품 수

# 스킬 문서 기준 기본 프록시 URL (환경변수로 재정의 가능)
PROXY_BASE_URL = os.environ.get("KSKILL_PROXY_BASE_URL", "https://k-skill-proxy.nomadamas.org").rstrip("/")
SEARCH_ENDPOINT = f"{PROXY_BASE_URL}/v1/naver-shopping/search"


def parse_delivery_fee(val) -> int:
    """
    배송비 값을 안전하게 정수로 변환합니다. (무료, None, 0 -> 0)
    """
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d]", "", val)
        return int(cleaned) if cleaned else 0
    return 0


def fetch_from_proxy(keyword: str, sort: str = "price_asc", limit: int = 20) -> list:
    """
    k-skill-proxy API를 호출하여 상품 데이터를 가져옵니다.
    실패 시 예외를 발생시켜 Fallback 로직으로 전환할 수 있도록 합니다.
    """
    params = urllib.parse.urlencode({
        "q": keyword,
        "sort": sort,
        "limit": limit
    })
    url = f"{SEARCH_ENDPOINT}?{params}"
    headers = {
        "User-Agent": "percent-bot/1.0",
        "Accept": "application/json"
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        if "items" in data and isinstance(data["items"], list):
            items = []
            for item in data["items"]:
                price = int(item.get("price", 0))
                deliv_fee = parse_delivery_fee(
                    item.get("delivery_fee") or item.get("shipping_fee") or item.get("deliveryPrice")
                )
                items.append({
                    "title": item.get("title", ""),
                    "price": price,
                    "delivery_fee": deliv_fee,
                    "total_price": price + deliv_fee,
                    "mall_name": item.get("mall_name", "네이버 쇼핑"),
                    "review_count": int(item.get("review_count", 0)),
                    "url": item.get("url", "링크 없음"),
                    "is_ad": bool(item.get("is_ad", False))
                })
            return items
        raise ValueError("API 응답에 'items' 필드가 누락되었습니다.")


def fetch_from_naver_direct(keyword: str) -> list:
    """
    네이버 통합 검색(Nexearch) 내 쇼핑 데이터 엔진을 직접 파싱하여 상품 목록 및 배송비를 수집합니다.
    프록시 서버 장애 시에도 무중단으로 실시간 상품 정보를 제공합니다.
    """
    query_encoded = urllib.parse.quote(keyword)
    url = f"https://search.naver.com/search.naver?where=nexearch&query={query_encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.naver.com/"
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8")

    # 네이버 쇼핑 초기 상태 JSON 데이터 추출
    m = re.search(
        r'naver\.search\.ext\.newshopping\["shopping"\]\._INITIAL_STATE\s*=\s*({.*?});?\s*(?:naver|var|\n|</script>)',
        html,
        re.DOTALL
    )
    if not m:
        raise ValueError("네이버 쇼핑 데이터 블록을 찾을 수 없습니다.")

    data = json.loads(m.group(1))
    slots = data.get("initProps", {}).get("pagedSlot", [])
    items = []

    for page in slots:
        for s in page.get("slots", []):
            d = s.get("data", {})
            # 광고 상품 여부 확인
            is_ad = (d.get("cardType") == "AD_CARD" or d.get("sourceType") == "AD")

            title = re.sub(r'<[^>]+>', '', d.get("productName", "")).strip()
            price_val = d.get("discountedSalePrice") or d.get("salePrice") or d.get("price") or d.get("lowPrice")
            if not title or not price_val:
                continue

            try:
                price = int(price_val)
            except (ValueError, TypeError):
                continue

            # 배송비 추출 (productDeliveryInfo 객체 내 deliveryFee)
            deliv_info = d.get("productDeliveryInfo", {})
            delivery_fee = 0
            if isinstance(deliv_info, dict):
                delivery_fee = parse_delivery_fee(deliv_info.get("deliveryFee"))
            elif isinstance(deliv_info, (int, str)):
                delivery_fee = parse_delivery_fee(deliv_info)

            mall_name = d.get("mallName")
            if not mall_name:
                mall_count = d.get("mallCount")
                mall_name = f"네이버 가격비교 ({mall_count:,}곳)" if mall_count else "네이버 쇼핑"

            review_count = d.get("totalReviewCount") or d.get("reviewCount") or 0
            try:
                review_count = int(review_count)
            except (ValueError, TypeError):
                review_count = 0

            # 링크 생성 (직접 링크 또는 카탈로그 링크)
            nv_mid = d.get("nvMid")
            click_url = d.get("productClickUrl", {})
            url = ""
            if isinstance(click_url, dict):
                url = click_url.get("pcUrl") or click_url.get("mobileUrl")
            elif isinstance(click_url, str):
                url = click_url

            if not url and nv_mid:
                url = f"https://search.shopping.naver.com/catalog/{nv_mid}"

            items.append({
                "title": title,
                "price": price,
                "delivery_fee": delivery_fee,
                "total_price": price + delivery_fee,
                "mall_name": mall_name,
                "review_count": review_count,
                "url": url or "링크 없음",
                "is_ad": is_ad
            })

    return items


def fetch_shopping_items(keyword: str, sort: str = "price_asc", limit: int = 20) -> list:
    """
    네이버 쇼핑 데이터를 조회합니다.
    1차로 스킬 프록시 API를 시도하고, 장애 발생 시 네이버 쇼핑 엔진에서 직접 수집합니다.
    값을 전혀 가져오지 못하면 지어내지 않고 오류 내용을 보고하며 종료합니다.
    """
    proxy_error_msg = ""
    try:
        items = fetch_from_proxy(keyword, sort, limit)
        if items:
            return items
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        proxy_error_msg = f"HTTP {e.code} 에러 (상세: {body[:300]})"
    except Exception as e:
        proxy_error_msg = str(e)

    print(f"ℹ️ [알림] 프록시 API 응답 불가 ({proxy_error_msg}) → 네이버 쇼핑 실시간 검색 Fallback 전환", file=sys.stderr)

    # Fallback: 네이버 쇼핑 직접 조회
    try:
        items = fetch_from_naver_direct(keyword)
        if items:
            return items
    except Exception as e:
        print(f"❌ [네이버 쇼핑 직접 수집 실패] {e}", file=sys.stderr)

    # 두 경로 모두 실패 시 지어내지 않고 오류 원인 보고 후 중단
    print("\n❌ [오류 발생] 네이버 쇼핑 상품 데이터를 가져오지 못했습니다.", file=sys.stderr)
    print(f"   • 프록시 오류: {proxy_error_msg}", file=sys.stderr)
    print("   • 원인: 외부 프록시 서버 및 네이버 쇼핑 응답 블록을 파싱할 수 없습니다.", file=sys.stderr)
    sys.exit(1)


def load_env(env_file: Path) -> dict:
    """
    .env 파일에서 환경변수를 읽어 딕셔너리로 반환합니다 (읽기 전용).
    """
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


def send_kakao_memo(item: dict) -> tuple[bool, str]:
    """
    카카오톡 '나에게 보내기' API를 호출하여 최저가 알림 메시지를 전송합니다.
    - .env의 KAKAO_ACCESS_TOKEN을 읽어와 사용합니다.
    - 상품명, 배송비 포함 가격, 쇼핑몰 이름, 리뷰 수 포함 및 링크 연결.
    """
    env_vars = load_env(ENV_PATH)
    access_token = env_vars.get("KAKAO_ACCESS_TOKEN")

    if not access_token:
        return False, ".env 파일에 KAKAO_ACCESS_TOKEN이 설정되어 있지 않습니다."

    title = item.get("title", "제목 없음").replace("<b>", "").replace("</b>", "").strip()
    if len(title) > 80:
        title = title[:77] + "..."

    price = item.get("price", 0)
    delivery_fee = item.get("delivery_fee", 0)
    total_price = item.get("total_price", price + delivery_fee)

    price_detail = f"{price:,}원"
    if delivery_fee > 0:
        price_detail += f" (+배송비 {delivery_fee:,}원 = 총 {total_price:,}원)"
    else:
        price_detail += " (무료배송)"

    mall_name = item.get("mall_name", "미표기 판매처")
    review_count = item.get("review_count", 0)
    url = item.get("url", "https://search.shopping.naver.com")

    # 텍스트 템플릿 구성
    text_content = (
        f"📱 [아이폰 13미니 특가 알림]\n\n"
        f"• 상품명: {title}\n"
        f"• 가격: {price_detail}\n"
        f"• 쇼핑몰: {mall_name}\n"
        f"• 리뷰 수: {review_count:,}개"
    )

    template_object = {
        "object_type": "text",
        "text": text_content,
        "link": {
            "web_url": url,
            "mobile_web_url": url
        },
        "buttons": [
            {
                "title": "구매하러 가기",
                "link": {
                    "web_url": url,
                    "mobile_web_url": url
                }
            }
        ]
    }

    send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    payload = urllib.parse.urlencode({
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }).encode("utf-8")

    req = urllib.request.Request(
        send_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            res = json.loads(body)
            if res.get("result_code") == 0:
                return True, "카카오톡 메시지 전송 성공 (result_code: 0)"
            return False, f"카카오 응답 오류: {body}"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        detailed_reason = f"HTTP {e.code} 에러: {err_body}"
        return False, detailed_reason
    except Exception as e:
        return False, f"요청 예외 발생: {e}"


def main():
    print("=" * 70)
    print("📱 네이버 쇼핑 최저가 알리미 봇 (percent_bot) 실행")
    print(f"🔍 검색 키워드 : '{KEYWORD}'")
    print(f"🎯 목표 기준가 : {TARGET_PRICE:,}원 (배송비 포함 실구매가 기준)")
    print("=" * 70)
    print()
    sys.stdout.flush()

    # 1. 네이버 쇼핑 검색 스킬로 데이터 수집
    raw_items = fetch_shopping_items(KEYWORD, sort=SORT_METHOD, limit=LIMIT)

    if not raw_items:
        print("❌ [조회 실패] 검색 결과 상품이 비어 있습니다.", file=sys.stderr)
        sys.exit(1)

    # 2. 반환된 광고 상품 제거 및 실제 상품 필터링
    clean_items = []
    for item in raw_items:
        # 광고 상품 플래그 확인 (is_ad 가 True 이면 제외)
        if item.get("is_ad") is True:
            continue
        # 유효 가격 및 제목 확인
        if item.get("price", 0) > 0 and item.get("title"):
            clean_items.append(item)

    if not clean_items:
        print("❌ [필터링 실패] 광고를 제외한 실제 상품 결과가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 3. 배송비 포함 저렴한 순서(total_price 오름차순)로 정렬
    clean_items.sort(key=lambda x: x.get("total_price", 999999999))

    # 상위 5개 상품 추출
    top_items = clean_items[:TOP_COUNT]

    print(f"📋 [배송비 포함 최저가 순위 TOP {len(top_items)} (광고 제외 실제 상품)]")
    print("-" * 70)

    for idx, item in enumerate(top_items, 1):
        title = item.get("title", "제목 없음").replace("<b>", "").replace("</b>", "").strip()
        price = item.get("price", 0)
        delivery_fee = item.get("delivery_fee", 0)
        total_price = item.get("total_price", price + delivery_fee)

        deliv_str = "무료배송" if delivery_fee == 0 else f"{delivery_fee:,}원"
        mall_name = item.get("mall_name", "미표기 판매처")
        review_count = item.get("review_count", 0)
        url = item.get("url", "링크 없음")

        print(f"[{idx}위] {title}")
        print(f"  • 배송비 포함 실구매가 : {total_price:,}원")
        print(f"  • 가격 상세            : 상품가 {price:,}원 + 배송비 {deliv_str}")
        print(f"  • 쇼핑몰               : {mall_name}")
        print(f"  • 리뷰 수              : {review_count:,}개")
        print(f"  • 해당 제품 링크       : {url}")
        print("-" * 70)

    print()

    # 4. 1위 가격이 목표가 300,000원 이하인지 점검 및 출력
    top_item = top_items[0]
    top_total_price = int(top_item.get("total_price", 0))

    print(f"📊 [목표 가격 점검] 1위 상품 실구매가: {top_total_price:,}원 vs 목표가: {TARGET_PRICE:,}원")
    if top_total_price <= TARGET_PRICE:
        diff = TARGET_PRICE - top_total_price
        print("🚨 [특가 발생] 목표 가격 이하입니다!")
        print(f"   (목표가 300,000원 대비 {diff:,}원 더 저렴합니다.)")

        # 카카오톡 알림 전송 (토큰이 있을 경우)
        env_vars = load_env(ENV_PATH)
        if env_vars.get("KAKAO_ACCESS_TOKEN"):
            print("\n📲 카카오톡 '나에게 보내기' 알림 전송 시도 중...")
            success, result_message = send_kakao_memo(top_item)
            if success:
                print(f"✅ [카카오톡 전송 성공] {result_message}")
            else:
                print(f"❌ [카카오톡 전송 실패] {result_message}")
    else:
        diff = top_total_price - TARGET_PRICE
        print("ℹ️ [유지] 아직 목표 가격보다 비쌉니다.")
        print(f"   (목표가 300,000원 대비 {diff:,}원 초과)")

    print("=" * 70)


if __name__ == "__main__":
    main()
