# 국내주식 단타 알림봇 설계서

## 1. 목표

5분봉 ICT/SMC 기반으로 **Bullish OB → BOS 돌파** 패턴을 실시간 감지해  
텔레그램으로 알림. 1단계는 알림만, 2단계는 자동 주문.

---

## 2. 신호 로직 (5분봉 ICT)

### 2-1. 핵심 개념

| 용어 | 정의 |
|------|------|
| **Swing High** | 좌우 N봉보다 고가가 높은 봉 |
| **Swing Low**  | 좌우 N봉보다 저가가 낮은 봉 |
| **BOS** (Break of Structure) | 직전 Swing High 상향 돌파 → 강세 구조 확정 |
| **Bullish OB** | BOS 직전 마지막 음봉 (기관 매집 자리) |
| **진입 자리** | 가격이 Bullish OB 구간 내 되돌림 + 양봉 마감 확인 |

### 2-2. 신호 발생 조건 (AND)

```
① 최근 30봉 내 Bullish OB 존재 (60봉 프레임 내 과거 30봉 탐색)
② 현재 봉이 OB 구간(ob_low ~ ob_high) 내 진입
③ 현재 봉 양봉 마감 (close >= open)
④ RVOL >= 1.3x (거래량 확인, 완화: 1.5→1.3)
⑤ 현재가 > 5분봉 VWAP (추세 방향 확인)
⑥ R (entry - sl) >= entry의 0.2% (손절폭 최소값 — 노이즈 필터)
```

### 2-3. 무효화 조건

```
- OB 하단 아래로 종가 이탈 시 해당 OB 삭제
- 당일 신고가 +20% 이상 (상한가 근접 추격 방지)
```

---

## 3. 아키텍처

```
main.py          ← 3분 주기 루프 (09:05~15:25)
  ├── scanner.py     ← 후보 선정 (거래증가율 Top50)
  ├── kis_client.py  ← 5분봉 조회 (FHKST03010200)
  ├── indicators.py  ← Swing Point / OB / BOS / RVOL / VWAP
  ├── signal.py      ← ICT 신호 생성 → DaySignal
  └── notify.py      ← 텔레그램 알림
config.py        ← 설정 (KIS 인증, 파라미터)
```

---

## 4. KIS API

| 용도 | TR_ID | 비고 |
|------|-------|------|
| 5분봉 조회 | `FHKST03010200` | 당일만, 페이지네이션으로 최대 60봉 수집 |
| 거래증가율 순위 | `FHPST01710000` | 후보 선정 |
| 현재가 | `FHKST01010100` | 가격 확인 |

**5분봉 파라미터 및 페이지네이션**
```
1차 호출:
  FID_ETC_CLS_CODE  = ""
  FID_COND_MRKT_DIV_CODE = "J"
  FID_INPUT_ISCD    = 종목코드
  FID_INPUT_HOUR_1  = "153000"   ← 당일 전체 (역순 최대 30봉)
  FID_PW_DATA_INCU_YN = "N"

페이지네이션:
  - 1차가 30봉 미만이면 종료 (장 초반)
  - 1차가 정확히 30봉이면 2차 호출
  - 2차: FID_INPUT_HOUR_1 = 1차 결과 가장 오래된 봉의 시각
  - 최종: 시간 기준 중복 제거, 과거→현재 오름차순 정렬
```

---

## 5. 설정 파라미터 (config.py)

```python
swing_n: int = 3              # 스윙 포인트 좌우 봉 수
ob_lookback: int = 30         # OB 탐색 범위(봉) — 60봉 프레임 내 과거 30봉
rvol_threshold: float = 1.3   # 단타 RVOL 최소값 (완화: 1.5→1.3)
min_r_pct: float = 0.2        # 최소 R 폭 (entry의 %) — 손절폭 최소값
rvol_window: int = 20         # RVOL 계산 윈도우
scan_interval: int = 180      # 스캔 주기(초) = 3분
top_n: int = 50               # 후보 종목 수
```

---

## 6. DaySignal 데이터 클래스

```python
@dataclass
class DaySignal:
    symbol: str
    ob_low: float      # Bullish OB 하단
    ob_high: float     # Bullish OB 상단
    entry_price: float # 현재가
    sl_price: float    # 손절 = OB 하단
    tp1_price: float   # 익절1 = entry + R
    tp2_price: float   # 익절2 = entry + 2R
    rvol: float
    vwap: float
    timestamp: str
```

---

## 7. 텔레그램 알림 형식

```
📊 [종목명] 123456 단타신호
OB구간: 12,500 ~ 12,800원
현재가: 12,650원
손절: 12,500원 (OB 하단) | R: 150원
익절1: 12,800원 (1R) | 익절2: 12,950원 (2R)
RVOL: 2.3x | VWAP: 12,420원
조건: OB진입✅ 양봉✅ RVOL✅ VWAP위✅
```

---

## 8. 운영 타임라인

| 시각 | 동작 |
|------|------|
| 09:05 | 스캔 시작 (동시호가 제외) |
| 09:05~15:25 | 3분 주기 스캔 |
| 15:25 | 스캔 종료 |
| 15:30 | idle |

---

## 9. 구현 현황

### 1단계 완료 ✅
- 5분봉 ICT/OB 신호 감지
- 텔레그램 알림 (손절/익절 라인 포함)
- 60봉 페이지네이션 (KIS 1콜 30봉 한계 보완)
- RVOL 1.3으로 완화 (저거래량 OB 되돌림 포함)
- R 최소폭 필터 (entry의 0.2% 이상)

### 2단계 (미구현)
- KIS 시장가 자동 주문
- 손절/익절 자동 관리 (주문 후 추적)
- 동일 종목 중복 알림 방지 (당일 1회)
