# percent_bot 🍜📱

네이버 쇼핑 검색 기반 실시간 최저가 탐지 및 카카오톡 '나에게 보내기' 특가 알림 봇입니다.

## ✨ 주요 기능
- **실시간 최저가 탐지**: 네이버 쇼핑 검색 결과를 실시간으로 파싱하여 광고 상품을 제외한 실제 최저가 TOP 순위를 추출합니다.
- **배송비 포함 실구매가 분석**: 무료배송 및 유료 배송비를 종합 계산하여 실제 최저가를 정확하게 점검합니다.
- **카카오톡 특가 알림**: 1위 가격이 설정된 목표가 이하일 때만 카카오톡 '나에게 보내기'로 알림을 전송합니다.
  - 알림 메시지 구성: 상품명, 가격, 쇼핑몰 이름, 리뷰 수, '구매하러 가기' 바로가기 버튼 링크 연동
  - 목표가보다 비쌀 경우 화면에만 상태를 표시하고 메시지는 발송하지 않습니다.
- **안전한 인증 관리**: 카카오 API 인증 키는 `.env`에서 읽어오며, 코드에 하드코딩되지 않습니다.

## 🚀 시작하기

### 1. 환경 설정
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 카카오 API 인증 키를 입력합니다:
```ini
KAKAO_REST_API_KEY=your_kakao_rest_api_key
KAKAO_CLIENT_SECRET=your_kakao_client_secret
KAKAO_REDIRECT_URI=http://localhost
KAKAO_REFRESH_TOKEN=your_kakao_refresh_token
KAKAO_ACCESS_TOKEN=your_kakao_access_token
```

### 2. 토큰 발급
카카오 인가 코드를 발급받은 후 토큰 발급 스크립트를 1회 실행합니다:
```bash
python get_kakao_token.py <인가코드>
```

### 3. 실행 방법
Windows 배치 파일 또는 파이썬 스크립트를 직접 실행합니다:
```bash
# 배치 파일 실행
percent_bot.bat

# 또는 파이썬 직접 실행
python percent_bot.py
```
