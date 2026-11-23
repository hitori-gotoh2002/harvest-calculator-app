"""월별 현금흐름 (현금흐름 달력의 계산부).

engine.py 의 날씨 경우별 손익(sims)을 '몇 월에 돈이 나가고 들어오는지'로 펼친다.
- 감가상각비(대농구·영농시설): 손익 비교(추천)에는 넣고(작물끼리 같은 기준), 자금 흐름 달력에는
  cash_only=True 로 빼서 실제 현금 지출만 쓴다(기계 교체 적립금은 선택 항목).
  EXCLUDE_DEP=True 이면 실제로 나가는 돈이 아니라고 보고 뺀다. 다만 작물별 비율이 조사마다 달라서
  (생산비조사 1~7%, 소득조사 10~38%) 작물끼리 비교할 때 왜곡이 생겨 기본값은 넣는 쪽이다.
- 돈이 나가는 시기: 파종 달 40% / 생육 중 30% / 수확 달 30% (가정, engine.ASSUME["cost_split"]).
  일손 사는 비용도 같은 비율. 관정 전기료는 생육 중.
- 돈이 들어오는 시기: 판매 대금은 작물별 첫 입금 월(crops.csv), 직불금·장려금은 수확 뒤 12월(가정).
금액 단위: 천 원 / 10a. 달 번호 0 = 파종하는 해 1월.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402

# 감가상각비(대농구 + 영농시설) ÷ 경영비. 현금이 나가지 않는 몫.
# 벼·콩·고추·마늘·양파: 국가데이터처 농산물생산비조사 2025 (2025 농산물소득자료집 전국판 별지 pp.236~240)
# 나머지: 농진청 농산물소득조사 2024 (2024 농산물소득자료집 전국판 작목별 소득동향)
DEP_SHARE = {
    "벼": (28573 + 2905) / 612346,
    "콩(논 재배)": (34059 + 4514) / 580606,
    "고추": (71637 + 38525) / 2648321,
    "마늘": (43652 + 7208) / 2897737,
    "양파": (23681 + 5332) / 2477103,
    "참깨": 222560 / 770302,
    "들깨": 134061 / 497644,
    "감자": 222638 / 1443511,     # 봄감자
    "고구마": 329255 / 1919252,
    "옥수수": 171573 / 852631,    # 노지풋옥수수
    "배추": 299791 / 1533753,     # 노지가을배추
    "무": 215116 / 1264566,       # 노지가을무
    "밀": 81474 / 314758,
    "보리": 126194 / 334139,      # 겉보리
}
EXCLUDE_DEP = False
SUBSIDY_MONTH = 12  # 직불금·장려금 받는 달 (가정: 공익직불 11~12월 지급)
N = 27              # 파종 해 1월부터 27개월 (겨울 작물·다음 해 입금까지)


# 판매 대금이 들어오는 달과 비율 (가정). 여러 번 나눠 받는 작물만 따로 적고,
# 나머지는 작물표 '첫입금월'의 기간(예: '9~11')에 똑같이 나눈다.
PAY_SCHEDULE = {
    "고추": {8: 0.2, 9: 0.3, 10: 0.3, 11: 0.2},  # 8~10월 여러 번 따서 말려 팔기
    "벼": {10: 0.4, 11: 0.4, 1: 0.2},            # 공공비축·농협 수매 우선지급금 10~11월, 최종 정산 다음 해 1월
}


def pay_schedule(row) -> list[tuple[int, float]]:
    """[(입금 달 1~12, 비율)]. 비율 합 = 1."""
    if row["작물"] in PAY_SCHEDULE:
        return list(PAY_SCHEDULE[row["작물"]].items())
    m = re.match(r"\s*(\d+)\s*~\s*(\d+)", str(row["첫입금월"]))
    if not m:
        return [(E.first_month(row["첫입금월"]), 1.0)]
    a, b = int(m.group(1)), int(m.group(2))
    months = [a]
    while months[-1] != b and len(months) < 12:
        months.append(months[-1] % 12 + 1)
    return [(x, 1 / len(months)) for x in months]


def _month(doy_abs: int) -> int:
    y, d = divmod(int(doy_abs), 365)
    return y * 12 + E.NONLEAP[d].month - 1


def _next(month_1_12: int, not_before: int) -> int:
    m = month_1_12 - 1
    while m < not_before:
        m += 12
    return m


def ledger(row, season: E.Season, f: E.Field, sim: dict, price: float = 1.0, cash_only: bool | None = None) -> np.ndarray:
    """한 작물 · 한 날씨 경우의 월별 자금 수지 (천 원/10a, 길이 N).
    cash_only=True 이면 감가상각비(현금 아님)를 빼고 실제 현금 지출만 쓴다. None 이면 EXCLUDE_DEP."""
    cash_only = EXCLUDE_DEP if cash_only is None else cash_only
    m = np.zeros(N)
    sow = _month(season.sow)
    end = _month(season.sow + season.length - 1)
    mids = list(range(sow + 1, end)) or [sow]
    cost = float(row["경영비_천원"])
    dep = DEP_SHARE.get(row["작물"], 0.0) * cost if cash_only else 0.0
    cash_cost = cost - dep + sim["labor"]
    a, b, c = E.ASSUME["cost_split"]
    m[sow] -= a * cash_cost
    for k in mids:
        m[k] -= (b * cash_cost + sim["elec"]) / len(mids)
    m[end] -= c * cash_cost
    for mon, share in pay_schedule(row):
        idx = _next(mon, sow)
        if row["작물"] not in PAY_SCHEDULE:
            idx = max(idx, end)  # 수확 끝나기 전 입금이면 수확 달 (engine.cash_need 와 같은 규칙)
        m[min(idx, N - 1)] += sim["revenue"] * price * share
    subsidy = sim["fixed"] + cost + sim["elec"] + sim["labor"]
    if abs(subsidy) > 1e-9:
        m[_next(SUBSIDY_MONTH, end)] += subsidy
    return m


def cash_net(row, sim: dict, price: float = 1.0, cash_only: bool | None = None) -> float:
    """한 해 순수입 = 손익 (+ cash_only 이면 감가상각비를 되더함 = 실제 현금 기준)."""
    cash_only = EXCLUDE_DEP if cash_only is None else cash_only
    dep = DEP_SHARE.get(row["작물"], 0.0) * float(row["경영비_천원"]) if cash_only else 0.0
    return sim["revenue"] * price + sim["fixed"] + dep


def plan_parts(r: dict, f: E.Field, plan: dict) -> list[tuple[str, float]]:
    """계획 → [(작물, 비율)]."""
    if plan["share"] <= 0:
        return [(f.current, 1.0)]
    if plan["share"] >= 1 or f.current not in r["results"]:
        return [(plan["alt"], 1.0)]
    return [(f.current, 1 - plan["share"]), (plan["alt"], plan["share"])]


def plan_cases(r: dict, f: E.Field, plan: dict, decision: str, with_price: bool = True, cash_only: bool | None = None):
    """계획의 날씨 경우(× 가격 경우)별 월별 자금 수지. 반환: (경우 이름 목록, 배열[경우, N], 한 해 순수입[경우]).
    cash_only=True: 실제 현금 기준(감가상각 제외), False: 손익 기준(감가상각을 기계 교체 적립금으로 포함)."""
    parts = plan_parts(r, f, plan)
    by = {}
    for crop, _ in parts:
        row, sims, _ = r["results"][crop]
        season, _ = E.plan_season(row, f, E.doy(decision))
        by[crop] = (row, season, {s["analog"]: s for s in sims})
    years = sorted(set.intersection(*[set(v[2]) for v in by.values()]))
    labels, rows, nets = [], [], []
    for y in years:
        pfs = {c: ((E.price_matrix([by[c][2][y]], float(by[c][0]["가격변동"]))[0]) if with_price else np.array([1.0]))
               for c, _ in parts}
        n_p = len(next(iter(pfs.values())))
        for k in range(n_p):
            led = np.zeros(N)
            net = 0.0
            for crop, w in parts:
                row, season, sm = by[crop]
                p = pfs[crop][k]
                led += w * ledger(row, season, f, sm[y], p, cash_only)
                net += w * cash_net(row, sm[y], p, cash_only)
            labels.append((y, k))
            rows.append(led)
            nets.append(net)
    return labels, np.array(rows), np.array(nets)


def realized_cash(f: E.Field, year: int, decision: str, plan_parts_list) -> float | None:
    """그해 실제 날씨(가격 기준값)로 계획대로 했을 때 한 해 순현금."""
    tot = 0.0
    for crop, w in plan_parts_list:
        v = E.realized(f, year, decision, crop)
        if v is None:
            return None
        row = E.crop_row(crop)
        tot += w * (v + (DEP_SHARE.get(crop, 0.0) * float(row["경영비_천원"]) if EXCLUDE_DEP else 0.0))
    return tot
