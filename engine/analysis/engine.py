"""물때달력 계산 엔진 (HANDOFF 4장, 2026-11-10 2차 설계).

질문: "올해 조건에서 평소 작부 계획(현재 작물)을 바꿔야 하나? 바꾼다면 면적의 몇 %를 무엇으로?"

계산 순서
1. 날씨 경우: 기준 날짜까지는 그해 실제 날씨(흙 마름·저수지 상태가 여기서 정해짐), 그 뒤는 과거 34개 해 날씨를 하나씩 이어 붙인다.
   (앞으로의 날씨를 '맞히는' 척하지 않는다. 비슷한 해만 고르는 방식은 백테스트에서 예측력이 없었다.)
2. 저수지(수혜구역): 전년 10월 1일부터 날마다 물이 들어오고(강수 × 유입계수) 논이 쓰는 만큼 빠진다.
   봄 가뭄이면 6월에 저수지가 덜 차 있고, 여름이 마르면 바닥나 벼가 물 부족을 겪는다. (설계기준: 10년 빈도 가뭄에 버티는 정도로 맞춤)
3. 물 부족(FAO-56 물통 모델): ETc = Kc × ET0. 뿌리층이 마르면 실제 증발산(ETa)이 줄어든다.
4. 수확 감소(FAO-33): 1 − Ya/Ym = Ky × (1 − ΣETa/ΣETc). 습해: 3일 강수 100mm 이상 횟수 × 작물 민감도 × 배수.
5. 손익(천 원/10a) = 총수입 × 수확비율 × 가격변동 − 경영비 − 급수 전기료 − 일손 부족분 고용비 + 직불금(논).
   '소득' 통계에는 농가 본인 노동값이 빠져 있으므로, 일손이 부족한 농가는 그 시간을 사람을 사서 채운다고 본다.
6. 비교: 현재 작물을 유지 / 일부(30·50·70%) 전환 / 전부 전환을 모두 계산해
   점수 = 0.5 × 평균 + 0.5 × '나쁜 20% 경우 평균'이 가장 높은 계획을 고른다.
7. 걸러내기: 파종 기한, 논/밭, 판로(직거래 필요 작물), 물 없는 논의 벼. (배수 나쁜 논의 습해는 빼지 않고 손실로 계산)

'가정'으로 정한 값은 모두 ASSUME에 모아 두었다.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# ---------------------------------------------------------------- 가정 값 (근거가 약함, 바꿀 수 있음)
ASSUME = dict(
    antecedent_days=90,        # 올해 상태를 볼 기간: 기준 날짜 전 90일 물수지
    analog_k=34,               # 기준 날짜 뒤 날씨로 쓸 과거 해 수. 34 = 그해를 뺀 전부.
                               # (실험: '비슷한 해 12개'만 쓰면 답만 자주 바뀌고 손익은 나아지지 않음 → 예측력 없음,
                               #  data/processed/validation_ablation.csv)
    price_on=True,             # 가격 변동 반영
    taw_field=100.0,           # 밭작물 뿌리층 유효수분(mm)
    taw_rice=60.0,             # 벼(논) 물 여유(mm)
    p_field=0.5,               # 밭작물 스트레스 시작 비율(FAO-56 기본값 근처)
    p_rice=0.2,                # 벼: 조금만 말라도 스트레스
    rice_percolation=3.0,      # 논 침투 손실(mm/일)
    rice_puddling=150.0,       # 모내기 전 써레질 물(mm)
    # 저수지(마을 공동): 2021~2025년 합천 저수지 82~85곳 실측 일별 저수율(5년)에 맞춤
    # (analysis/calibrate_reservoir.py, 5년 일별 오차 8.0%p. 2025 한 해로 맞춘 이전 값은 5년 오차 11.3%p)
    # 한계: 2022년 남부 가뭄의 깊이(실측 최저 35%)를 계산은 57%로 얕게 본다 → 저수지 가뭄 위험은 낮게 나온다.
    res_cap=2000.0,            # 저장량(수혜 논 면적 기준 mm 환산)
    res_inflow=0.6,            # 강수 1mm당 들어오는 물(mm)
    res_start=0.80,            # 전년 10월 1일 저수율(실측 2021~2024년 10월 1일 평균 80%)
    res_rice_sow="05-01",      # 이웃 논 물 대기 시작일(실측에서 5월 초부터 저수율이 빠짐)
    res_limit=0.30,            # 저수율 30% 밑이면 제한급수(필요량의 절반)
    res_empty=0.10,            # 저수율 10% 밑이면 농업용수 중단
    # 관정 하루 최대 급수(mm = m³/10a). 2026-11-23 5 → 10: 근거 없던 5mm는 작은 관정 수준. 논 관개용 750W 양수기 양수능력
    # 393.8 m³/일(1ha에 39mm, 유한선 외 2017 지하토양환경 22(4)), 양수장 지구 실측 1ha당 하루 120~210톤. 노후·가동률을 감안해
    # 보수적으로 10mm(1ha에 100톤). 5·15mm는 sensitivity.py에서 바꿔 본다.
    pump_mm_per_day=10.0,
    kwh_per_m3=0.3,            # 물 1m³ 퍼올리는 전력(kWh)
    wet_rain_3d=100.0,         # 습해 사건: 3일 강수 100mm 이상
    # 습해 '약함' 작물의 사건당 수확 감소(모형 날씨 큰비 1번당). 2026-11-22 실제 자료로 다시 맞춤(이전 0.05/0.15/0.40):
    # 보통 = 전국 콩 2009~2025 잔차 최소 0.06, 밀양 배수 시험 0.10 → 0.08 / 나쁨 = 김제 옥성 농가 0.09~0.16,
    # 암거 현장 시험 0.12 → 0.12 / 좋음 = 밭작물 도별 수확(analysis/real_check.py)과 맞아 그대로. 근거: HANDOFF 33~37장.
    # 주의: 기상청 관측은 큰비를 이 날씨의 약 두 배로 센다(real_check.py). 날씨 출처를 바꾸면 다시 맞춰야 한다.
    wet_loss={"좋음": 0.05, "보통": 0.08, "나쁨": 0.12},
    wet_sens_mult={"약함": 1.0, "보통": 0.5, "강함": 0.0},
    wage=15.0,                 # 고용 단가(천 원/시간). 2025 소득자료집 고용노동비÷시간 (마늘 14.7, 고추 15.0, 콩 15.9)
    labor_hire_share={"충분": 0.0, "보통": 0.5, "부족": 1.0},  # 본인 노동 중 사람을 사서 채워야 하는 비율
    # 2026-11-23: 일손 '충분'이어도 집에서 이 땅(1ha≈3,000평)에 한 철 낼 수 있는 시간에는 한계가 있다(가정).
    # 넘는 시간은 사람을 산다. 없으면(None) 예전처럼 '충분' = 본인 노동 0원.
    labor_own_cap=500.0,
    cost_split=(0.4, 0.3, 0.3),  # 경영비 지출: 파종 달 / 생육 중간 / 수확 달
    risk_weight=0.5,           # 점수 = (1−w)×평균 + w×나쁜 20% 평균
    switch_steps=(0.0, 0.3, 0.5, 0.7, 1.0),
    price_z=(-1.28, -0.52, 0.0, 0.52, 1.28),  # 가격 경우(정규분포 10·30·50·70·90% 지점)
    # 실제 통계로 '그해 묶음' (analysis/actual_shocks.py → data/processed/actual_shocks.csv)
    price_joint=True,          # 그 날씨 해의 실제 가격(물가 상승분 뺌)을 함께 씀. 자료 없는 해만 변동 폭 5가지
    other_hazard=True,         # 계산이 설명 못 한 그해 실제 수확 흔들림(냉해·태풍·병해충 등)을 곱함
    # 수입 기준 맞추기(2026-11-12): 작물표 총수입은 '평소 피해가 이미 들어간 실제 평균'인데, 계산 수확 비율은
    # '피해 없는 상태' 대비라 평소 피해를 두 번 빼게 된다. 그래서 통계가 대표하는 땅(actual_shocks.py와 같은
    # 대표 필지: 논 작물 = 저수지·배수 보통, 밭 작물 = 물 없음)의 34년 평균 수확 비율이 1이 되도록 작물마다
    # 한 번 나눈다. 땅마다 자기 평균으로 나누지 않으므로, 배수 나쁜 논 같은 땅의 추가 손해는 그대로 남는다.
    rev_calib=True,
)
TARIFF = {"갑": 48.3, "을": 65.9}  # 원/kWh, data/raw/kepco_agri_tariff.csv
SALES_OK = {"수매·계약만": {"수매·계약"}, "공판장까지": {"수매·계약", "공판장"},
            "직거래 가능": {"수매·계약", "공판장", "직거래 필요"}}
SEED_DEADLINE = {"콩(논 재배)": ("04-10", "콩 보급종 신청 마감(4/10) 지남 → 자가 채종·시중 종자 확보 필요")}

NONLEAP = [date(2001, 1, 1) + timedelta(days=i) for i in range(365)]


def doy(mmdd: str) -> int:
    m, d = map(int, mmdd.split("-"))
    return (date(2001, m, d) - date(2001, 1, 1)).days


# ---------------------------------------------------------------- 자료
@lru_cache(maxsize=None)
def regions() -> list[dict]:
    return list(csv.DictReader(open(RAW / "candidates.csv", encoding="utf-8")))


@lru_cache(maxsize=None)
def _weather_json():
    return json.load(open(RAW / "openmeteo_precip_et0_1991_2026.json", encoding="utf-8"))


@lru_cache(maxsize=None)
def weather(region: str) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """연도 → (강수 365일, ET0 365일). 2월 29일 제외, 자료 없는 날 NaN."""
    names = [r["name"] for r in regions()]
    d = _weather_json()[names.index(region)]["daily"]
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for t, p, e in zip(d["time"], d["precipitation_sum"], d["et0_fao_evapotranspiration"]):
        if t[5:] == "02-29":
            continue
        y = int(t[:4])
        if y not in out:
            out[y] = (np.full(365, np.nan), np.full(365, np.nan))
        i = doy(t[5:])
        out[y][0][i] = np.nan if p is None else p
        out[y][1][i] = np.nan if e is None else e
    return out


@lru_cache(maxsize=None)
def crops() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "crops.csv")


def crop_row(name: str):
    df = crops()
    return df[df["작물"] == name].iloc[0]


# ---------------------------------------------------------------- 입력
@dataclass
class Field:
    region: str = "합천"
    land: str = "논"              # 논 / 밭
    water: str = "수혜구역"        # 수혜구역(저수지) / 관정(전기) / 없음
    drainage: str = "보통"        # 좋음 / 보통 / 나쁨
    current: str = "벼"           # 평소 계획 작물
    free_from: str = "06-10"      # 앞그루(양파·마늘) 수확 뒤 쓸 수 있는 날. 없으면 "01-01"
    slot: str = "여름"            # 비교할 작기: 여름(3~7월 파종) / 겨울
    labor: str = "보통"           # 일손: 충분 / 보통 / 부족
    sales: str = "공판장까지"      # 판로: 수매·계약만 / 공판장까지 / 직거래 가능
    area_10a: float = 10.0        # 면적(10a 단위). 10 = 1ha = 약 3,000평
    use_obs: bool = True          # 실측 저수율이 있으면 기준 날짜의 저수지 상태를 실측값으로 바꿔 넣는다
    local_subsidy: dict = field(default_factory=dict)  # 지자체 추가 장려금(천 원/10a), 예: {"콩(논 재배)": 21} = 임실 ha당 210만 원
    sown: dict = field(default_factory=dict)  # 이미 심은 작물 → 심은 날("MM-DD"). 농사 중 다시 계산하기(recheck)용
    wet_from: str | None = None  # 이 날 전의 큰비 습해는 세지 않는다(재해 뒤 비교에서 현장 피해율로 대신 넣을 때)


@dataclass
class Season:
    sow: int
    length: int
    kc: np.ndarray


def kc_curve(row) -> np.ndarray:
    st = np.array([float(x) for x in str(row["단계일수"]).split("/")])
    L = int(row["생육일수"])
    st = st / st.sum() * L
    b = np.cumsum(st)
    t = np.arange(L) + 0.5
    ini, mid, end = row["Kc_ini"], row["Kc_mid"], row["Kc_end"]
    return np.where(t < b[0], ini,
           np.where(t < b[1], ini + (mid - ini) * (t - b[0]) / st[1],
           np.where(t < b[2], mid, mid + (end - mid) * (t - b[2]) / st[3])))


def plan_season(row, f: Field, decision_doy: int) -> tuple[Season | None, str]:
    if row["작물"] in f.sown:  # 이미 심은 작물: 심은 날 그대로 (기한·작기 검사는 심을 때 끝났다고 본다)
        return Season(doy(f.sown[row["작물"]]), int(row["생육일수"]), kc_curve(row)), ""
    s, e = doy(row["파종시작"]), doy(row["파종마감"])
    slot = "여름" if 3 <= int(row["파종시작"][:2]) <= 7 else "겨울"
    if slot != f.slot:
        return None, f"다른 작기({slot} 작물)"
    if f.land not in str(row["논밭"]):
        return None, f"{f.land}에 맞지 않음(표: {row['논밭']})"
    if row["판로"] not in SALES_OK[f.sales]:
        return None, f"판로 없음({row['판로']})"
    if f.water == "없음" and row["작물"] == "벼":
        return None, "물 댈 방법이 없으면 벼 재배 불가"
    sow = max(s, decision_doy, doy(f.free_from))
    if sow > e:
        return None, f"파종 기한({row['파종마감']}) 지남"
    return Season(sow, int(row["생육일수"]), kc_curve(row)), ""


# ---------------------------------------------------------------- 날씨 경우 (배열 0번 = 전년 1월 1일, 365번 = 기준 연도 1월 1일)
OFF = 365


def series(region: str, year: int, analog: int, decision_doy: int):
    W = weather(region)
    if year - 1 not in W or year not in W or analog not in W:
        return None
    nan = (np.full(365, np.nan), np.full(365, np.nan))
    prev, cur, ana, nxt = W[year - 1], W[year], W[analog], W.get(analog + 1, nan)
    P = np.concatenate([prev[0], cur[0][:decision_doy], ana[0][decision_doy:], nxt[0]])
    E = np.concatenate([prev[1], cur[1][:decision_doy], ana[1][decision_doy:], nxt[1]])
    return P, E


@lru_cache(maxsize=None)
def observed_rate(region: str, year: int):
    """농어촌공사 실측 일별 저수율(0~1, 365일). 2021~2025년 합천·강릉 (analysis/build_reservoir.py)."""
    path = ROOT / "data" / "processed" / "reservoir_daily_hapcheon_gangneung_2021_2025.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if region not in df.columns:
        return None
    s = df[region]
    s = s[(s.index.year == year) & ~((s.index.month == 2) & (s.index.day == 29))]
    if len(s) < 365:
        return None
    return s.values[:365] / 100.0


@lru_cache(maxsize=None)
def _shocks() -> dict:
    path = ROOT / "data" / "processed" / "actual_shocks.csv"
    if not path.exists():
        return {}
    d = pd.read_csv(path)
    return {(r["작물"], int(r["날씨연도"])): (float(r["기타재해"]), float(r["가격요인"])) for _, r in d.iterrows()}


def apply_shocks(row, sim: dict, year: int) -> dict:
    """그 날씨 해의 실제 기타 재해(수확)·가격 요인을 붙인다. 자료 없는 해는 그대로."""
    v = _shocks().get((row["작물"], int(year)))
    if v is None:
        return sim
    hz, pf = v
    if ASSUME.get("other_hazard", True):
        sim["revenue"] *= hz
        sim["yield_ratio"] *= hz
        sim["hazard"] = hz
    if ASSUME.get("price_joint", True) and ASSUME.get("price_on", True):
        sim["pf"] = pf
    return sim


def reservoir_traj(P, E, override: tuple[int, float] | None = None) -> np.ndarray:
    """마을 공동 저수지 저수량(mm) 날짜별. 전년 10/1 시작, 이웃 논(벼) 물 수요를 뺀다. 이 필지의 작물 선택과는 무관."""
    rice = crop_row("벼")
    kc = kc_curve(rice)
    s0 = OFF + doy(ASSUME["res_rice_sow"])
    cap, a = ASSUME["res_cap"], ASSUME["res_inflow"]
    S = np.full(len(P), np.nan)
    cur = ASSUME["res_start"] * cap
    for i in range(OFF - 92, len(P)):
        if np.isnan(P[i]) or np.isnan(E[i]):
            break
        d = 0.0
        if s0 <= i < s0 + len(kc):
            d = max(0.0, kc[i - s0] * E[i] + ASSUME["rice_percolation"] - P[i])
            if i < s0 + 10:
                d += ASSUME["rice_puddling"] / 10
        if override is not None and i == override[0]:
            cur = override[1]  # 실측 저수율로 바꿔 넣음 (그날 이후는 다시 계산)
        cur = max(0.0, min(cap, cur + a * P[i]) - d)
        S[i] = cur
    return S


def state_vector(region: str, year: int, decision_doy: int) -> tuple[float, float]:
    s = series(region, year, year, decision_doy)
    P, E = s
    i = OFF + decision_doy
    wb = float(np.nansum(P[i - ASSUME["antecedent_days"]:i] - E[i - ASSUME["antecedent_days"]:i]))
    return float(reservoir_traj(P, E)[i - 1]), wb


def analogs(region: str, year: int, decision_doy: int, exclude: set[int]) -> tuple[list[int], dict]:
    pool = [y for y in range(1992, 2026) if y not in exclude]
    now = state_vector(region, year, decision_doy)
    hist = {y: state_vector(region, y, decision_doy) for y in pool}
    R = np.array([v[0] for v in hist.values()])
    B = np.array([v[1] for v in hist.values()])
    sr, sb = R.std() or 1, B.std() or 1
    dist = {y: ((hist[y][0] - now[0]) / sr) ** 2 + ((hist[y][1] - now[1]) / sb) ** 2 for y in pool}
    chosen = sorted(pool, key=dist.get)[:ASSUME["analog_k"]]
    pct = float((B < now[1]).mean())
    rpct = float(((R < now[0]) + 0.5 * (R == now[0])).mean())
    state = "가뭄 주의" if min(pct, rpct) <= 0.2 else ("습해 주의" if pct >= 0.8 else "보통")
    return chosen, dict(reservoir_rate=round(100 * now[0] / ASSUME["res_cap"]), reservoir_pct=round(rpct, 2),
                        antecedent_wb=round(now[1]), wb_pct=round(pct, 2), state=state)


# ---------------------------------------------------------------- 한 작물 · 한 날씨 경우
def supply_factor(rate: float) -> float:
    if rate < ASSUME["res_empty"]:
        return 0.0
    return 0.5 if rate < ASSUME["res_limit"] else 1.0


_REV_REF: dict = {}


def rev_ref(row, region: str) -> float:
    """대표 필지의 34년(1992~2025) 평균 수확 비율(기타 재해 포함). 총수입을 이 값으로 나눠 '평소 평균 = 통계 평균'이 되게 한다."""
    import json
    key = (row["작물"], region, json.dumps(ASSUME, sort_keys=True, default=str))
    if key in _REV_REF:
        return _REV_REF[key]
    crop = row["작물"]
    winter = not (3 <= int(str(row["파종시작"])[:2]) <= 7)
    land = "논" if "논" in str(row["논밭"]) and crop in ("벼", "콩(논 재배)") else "밭"
    f = Field(region=region, land=land, water="수혜구역" if land == "논" else "없음", drainage="보통", current=crop,
              free_from="01-01", slot="겨울" if winter else "여름", sales="직거래 가능", use_obs=False)
    season, _ = plan_season(row, f, 0)
    vals = []
    if season is not None:
        for y in range(1992, 2026):
            s = series(region, y, y, 0)
            if s is None:
                continue
            r = simulate(row, f, season, *s, 0, calib=False)
            if r is None:
                continue
            hz = _shocks().get((crop, y), (1.0, 1.0))[0] if ASSUME.get("other_hazard", True) else 1.0
            vals.append(r["yield_ratio"] * hz)
    ref = float(np.mean(vals)) if len(vals) >= 10 else 1.0
    _REV_REF[key] = ref
    return ref


def labor_cost(row, f: "Field") -> float:
    """사람을 사서 채우는 일손 값(천 원/10a). 자가노동_h는 10a당 시간."""
    h = float(row["자가노동_h"])
    cap = ASSUME.get("labor_own_cap")
    if f.labor == "충분" and cap is not None:
        # 2026-11-23: 일손 '충분'이면 본인이 맡는 시간 = 한 철 상한(3,000평에 500시간)과 '보통' 수준 중 큰 쪽.
        # 이전에는 상한만 써서 자가노동이 10a당 100시간 넘는 작물(고추·참깨)에서 '충분'의 고용비가 '보통'보다 컸다.
        own = max(cap / 10.0, h * (1.0 - ASSUME["labor_hire_share"]["보통"]))
        return max(0.0, h - own) * ASSUME["wage"]
    return h * ASSUME["labor_hire_share"][f.labor] * ASSUME["wage"]


def simulate(row, f: Field, season: Season, P, E, decision_doy: int, override=None,
             obs_full: np.ndarray | None = None, calib: bool = True) -> dict | None:
    rice = row["작물"] == "벼"
    taw = ASSUME["taw_rice"] if rice else ASSUME["taw_field"]
    raw = (ASSUME["p_rice"] if rice else ASSUME["p_field"]) * taw
    s0, L = OFF + season.sow, season.length
    if s0 + L > len(P) or np.isnan(P[s0 - 60:s0 + L]).any() or np.isnan(E[s0 - 60:s0 + L]).any():
        return None
    # 마을 저수지에 물이 남아 있는 날만 물을 댈 수 있다 (수혜구역)
    Sx = None
    if f.water == "수혜구역":
        Sx = reservoir_traj(P, E, override)
        if obs_full is not None:  # 사후 평가: 그해 실측 저수율 그대로
            Sx[OFF:OFF + 365] = obs_full * ASSUME["res_cap"]
    avail = (lambda i: supply_factor(Sx[i] / ASSUME["res_cap"])) if Sx is not None else (lambda i: 1.0)
    # 파종 전 60일 맨땅 → 흙 마름 정도 (봄 가뭄 반영)
    dr = 0.0
    for i in range(s0 - 60, s0):
        dr = min(taw, max(0.0, dr - P[i] + 0.5 * E[i]))
    irr = 0.0
    if rice:  # 모내기 전 써레질 + 물 채우기
        need0 = ASSUME["rice_puddling"] + dr
        if f.water == "수혜구역":
            give = need0 * avail(s0)
        elif f.water == "관정":
            give = min(need0, ASSUME["pump_mm_per_day"] * 20)
        else:
            give = 0.0
        irr += give
        dr = max(0.0, need0 - give - ASSUME["rice_puddling"])
        dr = min(dr, taw)
    etc_sum = eta_sum = 0.0
    for k in range(L):
        i = s0 + k
        etc = season.kc[k] * E[i]
        dr = max(0.0, dr - P[i])
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        eta = ks * etc
        dr = min(taw, dr + eta + (ASSUME["rice_percolation"] if rice else 0.0))
        if dr > raw and f.water != "없음":
            want = dr
            if f.water == "관정":
                want = min(want, ASSUME["pump_mm_per_day"])
            if f.water == "수혜구역":
                want *= avail(i)
            dr -= want
            irr += want
        etc_sum += etc
        eta_sum += eta
    yr_water = max(0.0, 1 - float(row["Ky"]) * (1 - eta_sum / etc_sum))
    Ps = P[s0:s0 + L]
    r3 = np.convolve(Ps, np.ones(3), "valid")
    events, j = 0, 0
    w0 = OFF + doy(f.wet_from) if f.wet_from else -1  # 재해 뒤 비교: 이 날 전 큰비는 현장 피해율로 따로 넣음
    while j < len(r3):
        if r3[j] >= ASSUME["wet_rain_3d"]:
            events += 1 if s0 + j >= w0 else 0
            j += 3
        else:
            j += 1
    drain = f.drainage if f.land == "논" else "좋음"
    per = ASSUME["wet_loss"][drain] * ASSUME["wet_sens_mult"][row["습해"]]
    wet_loss = min(0.9, 1 - (1 - per) ** events)
    yr = yr_water * (1 - wet_loss)
    elec = irr * ASSUME["kwh_per_m3"] * (TARIFF["갑"] if rice else TARIFF["을"]) / 1000 if f.water == "관정" else 0.0
    labor = labor_cost(row, f)
    subsidy = (float(row["직불_천원"]) if f.land == "논" else 0.0) + float(f.local_subsidy.get(row["작물"], 0.0))
    if not ASSUME.get("subsidy_on", True):  # 화면의 '직불금 끄기'
        subsidy = 0.0
    fixed = -float(row["경영비_천원"]) - elec - labor + subsidy
    ref = rev_ref(row, f.region) if (calib and ASSUME.get("rev_calib", True)) else 1.0
    return dict(revenue=float(row["총수입_천원"]) * yr / ref, fixed=fixed, yield_ratio=yr, water_ratio=yr_water,
                wet_events=events, irrigation_mm=irr, elec=elec, labor=labor,
                season_wb=float(np.sum(Ps - E[s0:s0 + L])),
                reservoir_min=float(np.nanmin(Sx[s0:s0 + L]) / ASSUME["res_cap"]) if Sx is not None else None)


def price_factors(cv: float) -> np.ndarray:
    if not ASSUME.get("price_on", True):
        cv = 0.0
    z = np.array(ASSUME["price_z"])
    return np.exp(cv * z - cv * cv / 2)


def price_matrix(sims: list[dict], cv: float) -> np.ndarray:
    """(날씨 경우 × 가격 경우 5) 가격 배율. 그해 실제 가격이 있으면 5칸 모두 그 값(그해 묶음), 없으면 변동 폭 5가지."""
    spread = price_factors(cv)
    return np.array([np.full(len(spread), s["pf"]) if "pf" in s else spread for s in sims])


def profits(sims: list[dict], cv: float) -> np.ndarray:
    """(날씨 경우 × 가격 경우) 손익 표."""
    rev = np.array([s["revenue"] for s in sims])[:, None]
    fix = np.array([s["fixed"] for s in sims])[:, None]
    return rev * price_matrix(sims, cv) + fix


def score(x: np.ndarray) -> tuple[float, float, float]:
    v = np.sort(x.ravel())
    n20 = max(1, int(round(len(v) * 0.2)))
    w = ASSUME["risk_weight"]
    return (1 - w) * v.mean() + w * v[:n20].mean(), v.mean(), v[:n20].mean()


# ---------------------------------------------------------------- 현금 흐름
def first_month(text: str) -> int:
    return int(re.match(r"\d+", str(text)).group())


def cash_need(row, season: Season, f: Field) -> dict:
    sow_m = NONLEAP[season.sow % 365].month
    mid_m = NONLEAP[(season.sow + season.length // 2) % 365].month
    end_m = NONLEAP[(season.sow + season.length - 1) % 365].month
    pay = first_month(row["첫입금월"])
    after = lambda m: (m - sow_m) % 12  # noqa: E731
    pay_k = after(pay)
    if pay_k < after(end_m):
        pay_k, pay = after(end_m), end_m
    cost = float(row["경영비_천원"]) + labor_cost(row, f)
    a, b, c = ASSUME["cost_split"]
    spent = sum(x * cost for x, m in [(a, sow_m), (b, mid_m), (c, end_m)] if after(m) <= pay_k)
    return dict(첫입금전현금=round(spent), 첫입금월=pay, 입금까지개월=pay_k)


# ---------------------------------------------------------------- 비교
def obs_override(f: Field, year: int, ddoy: int):
    """기준 날짜 전날까지의 실측 저수율 → (배열 위치, 저수량 mm). 실측이 없으면 None."""
    if not f.use_obs or f.water != "수혜구역":
        return None
    obs = observed_rate(f.region, year)
    if obs is None or ddoy < 1 or np.isnan(obs[ddoy - 1]):
        return None
    return (OFF + ddoy, float(obs[ddoy - 1]) * ASSUME["res_cap"])


def run_crop(row, f: Field, year: int, ddoy: int, years: list[int]):
    season, why = plan_season(row, f, ddoy)
    if season is None:
        return None, why
    sims = []
    ov = obs_override(f, year, ddoy)
    for h in years:
        s = series(f.region, year, h, ddoy)
        if s is not None:
            r = simulate(row, f, season, *s, ddoy, override=ov)
            if r:
                r["analog"] = h
                sims.append(apply_shocks(row, r, h))
    if len(sims) < 3:
        return None, "날씨 자료 부족"
    return (season, sims), ""


def compare(f: Field, year: int, decision: str, exclude_years: set[int] | None = None) -> dict:
    ddoy = doy(decision)
    years, st = analogs(f.region, year, ddoy, set(exclude_years or set()) | {year})
    results, excluded, rows = {}, [], []
    for _, row in crops().iterrows():
        out, why = run_crop(row, f, year, ddoy, years)
        if out is None:
            excluded.append(dict(작물=row["작물"], 이유=why))
            continue
        season, sims = out
        pr = profits(sims, float(row["가격변동"]))
        results[row["작물"]] = (row, sims, pr)
        sc, mean, bad = score(pr)
        wbs = np.array([s["season_wb"] for s in sims])
        n = max(1, int(round(len(sims) * 0.2)))
        note = ""
        if row["작물"] in SEED_DEADLINE and ddoy > doy(SEED_DEADLINE[row["작물"]][0]):
            note = SEED_DEADLINE[row["작물"]][1]
        rows.append(dict(
            작물=row["작물"], 파종일=NONLEAP[season.sow].strftime("%m-%d"), 점수=sc, 평균손익=mean, 나쁜20평균=bad,
            가뭄해손익=pr[np.argsort(wbs)[:n]].mean(), 비많은해손익=pr[np.argsort(wbs)[-n:]].mean(), 최악=pr.min(),
            물부족수확비율=np.mean([s["water_ratio"] for s in sims]), 습해횟수=np.mean([s["wet_events"] for s in sims]),
            추가급수비=np.mean([s["elec"] for s in sims]), 일손비용=sims[0]["labor"],
            **cash_need(row, season, f), 비고=note))
    if not rows:  # 이 땅·이 날짜에 심을 수 있는 작물이 하나도 없음 (예: 늦여름의 여름 작기)
        raise ValueError("이 조건에서 심을 수 있는 작물이 없습니다")
    table = pd.DataFrame(rows).sort_values("점수", ascending=False).reset_index(drop=True)
    table.index += 1
    plan = recommend(f, results)
    ov = obs_override(f, year, ddoy)
    if ov is not None:
        rate = ov[1] / ASSUME["res_cap"]
        st = {**st, "reservoir_rate": round(100 * rate), "reservoir_source": "실측",
              "state": "가뭄 주의" if rate < 0.6 else st["state"]}
    return dict(table=table, excluded=pd.DataFrame(excluded), analog_years=years, state=st, plan=plan, results=results,
                breakeven=breakeven(f, results))


def recommend(f: Field, results: dict) -> dict:
    """현재 작물 유지 vs 일부·전부 전환. 같은 날씨 경우끼리 짝지어(가격은 작물별로 따로) 점수를 낸다."""
    cur = f.current
    if cur not in results:
        base = None
    else:
        base = results[cur]
    best = dict(plan="현재 유지", alt=cur, share=0.0)
    if base is None:  # 현재 작물을 못 심는 경우: 단일 작물 1위
        name = max(results, key=lambda k: score(results[k][2])[0])
        sc = score(results[name][2])
        return dict(plan=f"현재 작물({cur}) 불가 → {name}", alt=name, share=1.0, score=sc[0], mean=sc[1], bad=sc[2],
                    keep_score=None)
    b_row, b_sims, b_pr = base
    keep = score(b_pr)
    best.update(score=keep[0], mean=keep[1], bad=keep[2], keep_score=keep[0])
    b_by = {s["analog"]: i for i, s in enumerate(b_sims)}
    for name, (row, sims, pr) in results.items():
        if name == cur:
            continue
        idx = [(b_by[s["analog"]], i) for i, s in enumerate(sims) if s["analog"] in b_by]
        if len(idx) < 3:
            continue
        bi, ai = zip(*idx)
        B = b_pr[list(bi)][:, :, None]   # 날씨 × 현재 가격 × 1
        A = pr[list(ai)][:, None, :]     # 날씨 × 1 × 대안 가격
        for x in ASSUME["switch_steps"][1:]:
            sc = score((1 - x) * B + x * A)
            if sc[0] > best["score"] + 1e-9:
                best = dict(plan=f"{int(x * 100)}% → {name}", alt=name, share=x, score=sc[0], mean=sc[1],
                            bad=sc[2], keep_score=keep[0])
    return best


def breakeven(f: Field, results: dict) -> pd.DataFrame:
    """답이 뒤집히는 조건. 대안 작물마다 '전부 바꾸기'가 '현재 유지'와 같아지려면
    (1) 대안의 직불금이 10a당 얼마 더(덜) 있어야 하는지, (2) 현재 작물 가격이 몇 % 바뀌어야 하는지.
    점수(평균 50% + 나쁜 20% 평균 50%) 기준. 직불은 모든 경우에 같은 금액을 더하므로 점수 차이와 같다."""
    cur = f.current
    if cur not in results:
        return pd.DataFrame()
    c_row, c_sims, c_pr = results[cur]
    c_score = score(c_pr)[0]
    rev = np.array([s["revenue"] for s in c_sims])[:, None] * price_matrix(c_sims, float(c_row["가격변동"]))
    fix = np.array([s["fixed"] for s in c_sims])[:, None]
    rows = []
    for name, (row, sims, pr) in results.items():
        if name == cur:
            continue
        a_score = score(pr)[0]
        gap = c_score - a_score  # 양수면 대안이 그만큼 뒤짐
        lo, hi = 0.0, 3.0         # 현재 작물 가격 배율 m: score(rev*m+fix) = a_score
        if score(rev * lo + fix)[0] > a_score or score(rev * hi + fix)[0] < a_score:
            m = None
        else:
            for _ in range(40):
                mid = (lo + hi) / 2
                if score(rev * mid + fix)[0] > a_score:
                    hi = mid
                else:
                    lo = mid
            m = (lo + hi) / 2
        rows.append(dict(대안=name, 점수차_천원=round(gap, 1),
                         대안직불_추가필요_천원=round(max(gap, 0.0), 1),
                         현재작물가격_변화필요_퍼센트=None if m is None else round((m - 1) * 100, 1),
                         지금판단="대안이 이미 앞섬" if gap <= 0 else "현재 작물이 앞섬"))
    return pd.DataFrame(rows).sort_values("점수차_천원").reset_index(drop=True)


def realized(f: Field, year: int, decision: str, crop: str) -> float | None:
    """그해 실제 날씨로 그 작물을 키웠을 때 손익. 과거 모의시험(채점)용.
    그해 실제 가격·기타 재해 자료가 있으면 함께 쓰고(price_joint·other_hazard), 없으면 가격은 기준값."""
    ddoy = doy(decision)
    row = crop_row(crop)
    season, _ = plan_season(row, f, ddoy)
    if season is None:
        return None
    s = series(f.region, year, year, ddoy)
    obs = observed_rate(f.region, year) if (f.use_obs and f.water == "수혜구역") else None
    r = None if s is None else simulate(row, f, season, *s, ddoy, obs_full=obs)
    if r is None:
        return None
    r = apply_shocks(row, r, year)
    return r["revenue"] * r.get("pf", 1.0) + r["fixed"]


def realized_plan(f: Field, year: int, decision: str, plan: dict) -> float | None:
    cur = realized(f, year, decision, f.current) if plan["share"] < 1 else 0.0
    alt = realized(f, year, decision, plan["alt"]) if plan["share"] > 0 else 0.0
    if cur is None or alt is None:
        return None
    return (1 - plan["share"]) * cur + plan["share"] * alt


# ---------------------------------------------------------------- 농사 중 다시 계산하기 (2026-11-21)
def progress(row, f: Field, season: Season, year: int, ddoy: int) -> dict:
    """심은 날부터 기준 날짜 전날까지, 그해 실제 날씨로 지금까지 겪은 일을 정리한다."""
    n = int(min(season.length, max(0, ddoy - season.sow)))
    out = dict(지난날수=n, 생육일수=season.length, 진행률=n / season.length)
    W = weather(f.region)
    if n == 0 or year not in W:
        return out
    s = series(f.region, year, year, ddoy)
    part = Season(season.sow, n, season.kc[:n])
    r = simulate(row, f, part, *s, ddoy, override=obs_override(f, year, ddoy), calib=False)
    rain = float(np.nansum(W[year][0][season.sow:season.sow + n]))
    past = np.array([np.nansum(W[y][0][season.sow:season.sow + n]) for y in range(1992, year) if y in W])
    out.update(비=rain, 평년비=float(past.mean()), 비순위=float((past < rain).mean()),  # 0 = 지난해들보다 가장 적음
               비보다적은해=int((past < rain).sum()), 비교해수=len(past),
               증발=float(np.nansum(W[year][1][season.sow:season.sow + n])))
    if r:
        ky = float(row["Ky"])
        out.update(큰비횟수=int(r["wet_events"]), 물충족률=1 - (1 - r["water_ratio"]) / ky if ky > 0 else 1.0,
                   저수지최저=r["reservoir_min"])
    return out


def recheck(f: Field, year: int, today: str, exclude_years: set[int] | None = None) -> dict:
    """농사 중 다시 계산하기: f.sown 에 적은 '이미 심은 작물'의 전망을 today 기준으로 다시 계산한다.

    심은 날부터 today 전날까지는 그해 실제 날씨, today 부터는 지난 해들의 날씨를 하나씩 이어 붙인다
    (compare 와 같은 방식이라 심는 날의 전망과 바로 견줄 수 있다). 앞으로의 날씨를 맞히지는 않는다.
    가격과 기타 재해는 이어 붙인 해의 값을 쓴다. 결과의 results 는 compare() 와 모양이 같아
    cashflow.plan_cases 에 그대로 넣을 수 있다."""
    if not f.sown:
        raise ValueError("심은 작물(sown)이 없습니다")
    ddoy = doy(today)
    years, st = analogs(f.region, year, ddoy, set(exclude_years or set()) | {year})
    results, so_far = {}, {}
    for crop in f.sown:
        row = crop_row(crop)
        out, why = run_crop(row, f, year, ddoy, years)
        if out is None:
            raise ValueError(f"{crop}: {why}")
        season, sims = out
        results[crop] = (row, sims, profits(sims, float(row["가격변동"])))
        so_far[crop] = progress(row, f, season, year, ddoy)
    return dict(results=results, so_far=so_far, state=st, analog_years=years, today=today)


# ---------------------------------------------------------------- 재해 뒤 세 가지 비교 (2026-11-21)
def wet_damage(row, f: Field, events: int) -> float:
    """큰비 n번에 따른 수확 감소율(모형 가정: 배수 상태 × 작물 민감도)."""
    drain = f.drainage if f.land == "논" else "좋음"
    per = ASSUME["wet_loss"][drain] * ASSUME["wet_sens_mult"][row["습해"]]
    return min(0.9, 1 - (1 - per) ** events)


def after_disaster(f: Field, year: int, crop: str, hit: str, damage: float | None = None,
                   fix_cost: float = 0.0, fix_share: float = 0.0, fix_support: float = 0.0,
                   replant_support: float = 0.0, exclude_years: set[int] | None = None) -> dict:
    """재해가 난 날(hit) 이미 심은 작물(f.sown[crop])을 두고 세 가지 안의 한 해 손익(천 원/10a)을 견준다.

    - 그대로 두기: 재해 피해율(damage, 0~1)만큼 수확이 줄어든 채 끝까지 키운다. 재해 뒤 날씨(또 오는 큰비·가뭄)는
      그해 실제 날씨 + 지난 해들 날씨로 계산한다. damage 를 안 주면 모형이 본 피해(재해 날까지의 큰비 횟수)를 쓴다.
    - 되살리기: 비용 fix_cost 를 더 들여 피해의 fix_share 만큼을 되살린다(가정, 현장 확인 필요). fix_support = 농약대 등 지원.
    - 다시 심기: 갈아엎고 hit 뒤에 심을 수 있는 작물을 새로 심는다. 이미 쓴 돈(sunk)은 돌아오지 않고,
      원래 작물의 남은 비용·수입·직불금은 없어진다. replant_support = 대파대 등 지원.
    이미 쓴 돈 = 경영비·고용 일손비 중 심는 달 40% + 키우는 기간 30% × 지난 비율 (돈 나가는 시기 가정과 같음).
    """
    row = crop_row(crop)
    ddoy = doy(hit)
    fs = replace(f, wet_from=hit)
    years, st = analogs(f.region, year, ddoy, set(exclude_years or set()) | {year})
    out, why = run_crop(row, fs, year, ddoy, years)
    if out is None:
        raise ValueError(f"{crop}: {why}")
    season, sims = out
    sofar = progress(row, f, season, year, ddoy)
    model_damage = wet_damage(row, f, int(sofar.get("큰비횟수", 0)))
    p = model_damage if damage is None else float(damage)
    rev = np.array([s["revenue"] for s in sims])[:, None]
    fix = np.array([s["fixed"] for s in sims])[:, None]
    PM = price_matrix(sims, float(row["가격변동"]))
    keep = rev * (1 - p) * PM + fix
    repair = rev * (1 - p * (1 - fix_share)) * PM + fix - fix_cost + fix_support
    spent_share = ASSUME["cost_split"][0] + ASSUME["cost_split"][1] * min(1.0, sofar["진행률"])
    sunk = spent_share * (float(row["경영비_천원"]) + sims[0]["labor"])
    # 다시 심기: 재해 날 뒤에 심어 그해 안에 거두는 작물 (여름 작물, 가을 배추·무)
    replant, replant_info, next_year = {}, {}, []
    for slot in ("여름", "겨울"):
        f2 = replace(f, sown={}, wet_from=None, free_from=hit, slot=slot)
        try:
            r2 = compare(f2, year, hit, exclude_years)
        except ValueError:
            continue
        for name, (row2, sims2, pr2) in r2["results"].items():
            if name in replant or name in next_year:
                continue
            t = r2["table"][r2["table"]["작물"] == name].iloc[0]
            if doy(t["파종일"]) + int(row2["생육일수"]) > 365:  # 해를 넘기는 작물(마늘·양파·보리·밀)은 그대로 두기 뒤에도
                next_year.append(name)                        # 심을 수 있어 같은 해 비교에서 뺀다
                continue
            replant[name] = pr2 - sunk + replant_support
            replant_info[name] = dict(파종일=t["파종일"], 첫입금월=int(t["첫입금월"]))
    abandon = np.full_like(keep, -sunk + replant_support)  # 갈아엎고 비워 두기
    return dict(keep=keep, repair=repair, replant=replant, replant_info=replant_info, next_year=next_year,
                abandon=abandon, sunk=sunk, model_damage=model_damage, damage=p, so_far=sofar, season=season,
                analog_years=years)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for y in (2026, 2017, 2022):
        res = compare(Field(), y, "06-01")
        print(y, "상태:", res["state"], "\n  추천:", res["plan"]["plan"], "| 유사 연도:", res["analog_years"])
        print(res["table"][["작물", "점수", "평균손익", "나쁜20평균", "물부족수확비율", "일손비용", "비고"]].round(2).to_string())
