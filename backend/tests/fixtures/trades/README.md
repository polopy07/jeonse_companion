# 실거래가 API 응답 예시

`client.py`의 응답 해석과 수집을 테스트하는 가상 응답이다. 단지 이름·금액은 가상이다.

- `apt_trade.xml`: 아파트 매매 (aptNm, dealAmount, cdealType)
- `rh_rent.xml`: 연립다세대 전월세 (mhouseNm, deposit, monthlyRent)
- `auth_error.xml`: 인증키 오류 형식 (OpenAPI_ServiceResponse)

태그 이름은 공공데이터포털 실거래가 API(2024년 이후 영문 태그)를 기준으로 했다. 실제 응답으로 확인하면 이 파일을 실제 응답에서 잘라낸 것으로 바꾼다.
