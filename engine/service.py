"""수확계산기 계산 서비스: 화면 입력 → 엔진 → 화면에 쓸 숫자.

- 엔진(analysis/engine.py, cashflow.py, recheck.py)은 분석 저장소(multtae_handoff/analysis)와 같은 파일을 그대로 쓴다.
  숫자가 기획안과 같게 나오도록 엔진은 고치지 않는다. 고칠 일이 있으면 분석 저장소에서 고친 뒤 복사한다.
- 엔진 금액 단위는 천 원/10a. 화면 금액은 입력한 면적 기준 만 원(= 천 원/10a × 면적(10a) ÷ 10).
- '경우' = 34개 날씨 해 × 가격 5가지(170가지). 비율은 확률이 아니라 경우 중 비율.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "analysis"))
import cashflow as C  # noqa: E402
import engine as E  # noqa: E402
import recheck as R  # noqa: E402

YEAR = 2026
START, TARGET = 4, 13  # 자금 계산: 5월부터 다음 해 2월까지 (analysis/funds.py 와 같음)
OBS_RESERVOIR = {"합천", "강릉"}  # 저수지 일별 실측이 연결된 지역
PREV = {"없음": "01-01", "양파·마늘 거둔 뒤": "06-10"}
WATER = {"수혜구역", "관정", "없음"}
LEVEL = {"좋음", "보통", "나쁨"}
LABOR = {"충분", "보통", "부족"}


PUMP = {"일반": 10.0, "작은": 5.0, "큰": 15.0}  # 관정 하루 최대 급수(mm). 엔진 기본 10, 기획안 '작은 관정' 5
PAY_MODES = {"default", "once", "late"}


class InputError(ValueError):
    """화면에 그대로 보여 줄 수 있는 입력 오류."""


def num(d: dict, key: str, default: float, lo: float, hi: float, label: str, allow_none: bool = False):
    """숫자 입력을 안전하게 읽는다. 비었거나(None·'') 숫자가 아니거나 범위를 벗어나면 화면용 오류.
    allow_none 이면 값이 없을 때(키가 없거나 빈 칸) None 을 돌려준다 — '비우면 계산값' 칸(피해율·공사비 등)."""
    v = d.get(key, None if allow_none else default)
    if v is None or v == "":
        if allow_none:
            return None
        v = default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise InputError(f"{label}에는 숫자를 넣어 주세요")
    if x != x or not lo <= x <= hi:  # NaN 또는 범위 밖
        rng = f"{lo * 100:,.0f}~{hi * 100:,.0f}%" if (lo, hi) == (0, 1) else f"{lo:,.0f}~{hi:,.0f}"
        raise InputError(f"{label}은(는) {rng} 사이로 넣어 주세요")
    return x


@contextmanager
def scenario(d: dict):
    """화면에서 바꾼 조건(관정 크기·올해 값·입금 방식)을 엔진 가정에 잠깐 넣었다가 되돌린다.

    - pump: 관정 하루 급수 '일반'(10mm)·'작은'(5mm)·'큰'(15mm)
    - rev_pct: {작물: 판매수입 변화 %} — 올해 예상 값 (기획안 '앱에서 올해 예상 값을 넣고')
    - pay_crop, pay_mode: 그 작물 대금을 기본 일정 / 첫 입금 달에 한 번에(once) / 절반은 3달 늦게(late)
    요청은 http_util.LOCK 으로 한 번에 하나씩만 돌므로 전역 값을 바꿔도 다른 요청과 섞이지 않는다.
    """
    crops = E.crops()
    saved = (E.ASSUME["pump_mm_per_day"], crops["총수입_천원"].copy(), dict(C.PAY_SCHEDULE))
    try:
        pump = d.get("pump", "일반")
        if pump not in PUMP:
            raise InputError("관정 크기를 다시 골라 주세요")
        E.ASSUME["pump_mm_per_day"] = PUMP[pump]
        names = set(crops["작물"])
        rev = d.get("rev_pct") or {}
        if not isinstance(rev, dict):
            raise InputError("올해 값은 {작물: %} 형식으로 넣어 주세요")
        for crop, pct in rev.items():
            if crop not in names:
                raise InputError(f"올해 값을 넣은 작물({crop})을 찾을 수 없어요")
            try:
                pct = float(pct or 0)
            except (TypeError, ValueError):
                raise InputError(f"{nm(crop)} 올해 값 변화에는 숫자를 넣어 주세요")
            if pct != pct or not -50 <= pct <= 100:
                raise InputError("올해 값 변화는 −50%~+100% 사이로 넣어 주세요")
            i = crops.index[crops["작물"] == crop][0]
            crops.loc[i, "총수입_천원"] = float(saved[1].loc[i]) * (1 + pct / 100)
        mode, pc = d.get("pay_mode", "default"), d.get("pay_crop")
        if pc is not None and not isinstance(pc, str):
            raise InputError("대금 방식을 바꿀 작물을 다시 골라 주세요")
        if mode not in PAY_MODES:
            raise InputError("대금 받는 방식을 다시 골라 주세요")
        if pc and mode != "default":
            if pc not in names:
                raise InputError("대금 방식을 바꿀 작물을 다시 골라 주세요")
            first = base_schedule(pc)[0][0]
            C.PAY_SCHEDULE[pc] = {first: 1.0} if mode == "once" else {first: 0.5, (first + 2) % 12 + 1: 0.5}
        yield
    finally:
        E.ASSUME["pump_mm_per_day"] = saved[0]
        crops["총수입_천원"] = saved[1]
        C.PAY_SCHEDULE.clear()
        C.PAY_SCHEDULE.update(saved[2])


BASE_PAY = {k: dict(v) for k, v in C.PAY_SCHEDULE.items()}  # 바꾸기 전 기본 입금 일정


def base_schedule(crop: str) -> list[tuple[int, float]]:
    if crop in BASE_PAY:
        return list(BASE_PAY[crop].items())
    row = E.crop_row(crop).copy()
    row["작물"] = "__기본__"  # scenario 가 바꾼 PAY_SCHEDULE 를 건너뛰고 작물표의 입금 시기로 계산
    return C.pay_schedule(row)


def pay_options(crop: str) -> list[dict]:
    """대금 받는 방식 선택지(달 표시)."""
    sched = base_schedule(crop)
    first = sched[0][0]
    late = (first + 2) % 12 + 1
    base = ", ".join(f"{m}월 {round(w * 100)}%" for m, w in sched)
    return [dict(mode="default", text=f"기본: {base}"), dict(mode="once", text=f"{first}월에 한 번에"),
            dict(mode="late", text=f"절반은 {first}월, 절반은 {late}월 (3달 늦게)")]


# ---------------------------------------------------------------- 자금 (analysis/funds.py 와 같은 계산)
def household(L, living=0.0, start=START, target=TARGET):
    c = L.cumsum(1)[:, start:target + 1]
    return c - living * (np.arange(c.shape[1]) + 1)[None, :]


def fund_need(L, living=0.0, need=200.0):
    """L: 경우 × 달 현금 수지(만 원). 반환: 수확 전 운영자금, 필요한 시작 자금, 작물 수지만의 목표 달 잔액."""
    crop = L.cumsum(1)[:, START:TARGET + 1]
    med_step = np.median(np.diff(crop, axis=1), 0)
    first_pay = next((j + 1 for j, v in enumerate(med_step) if v > 1e-6), crop.shape[1])
    c = household(L, living)
    op = np.maximum(0, -c[:, :first_pay].min(1))
    start = np.maximum(np.maximum(0, -c.min(1)), need - c[:, -1])
    return op, start, crop[:, -1]


# ---------------------------------------------------------------- 이름·입력
def mmdd_ok(v, label: str) -> str:
    """'MM-DD' 날짜를 검사한다 (2026년 달력에 있는 날만, 2월 29일 없음). 틀리면 화면용 오류."""
    if not isinstance(v, str) or len(v) != 5 or v[2] != "-" or not (v[:2] + v[3:]).isdigit():
        raise InputError(f"{label}을 다시 넣어 주세요 (예: 06-10)")
    try:
        date(YEAR, int(v[:2]), int(v[3:]))
    except ValueError:
        raise InputError(f"{label}은 없는 날짜예요 ({v})")
    return v


def nm(c: str) -> str:
    return "논콩" if c == "콩(논 재배)" else c


def parts_of(f, plan):
    if plan["share"] <= 0:
        return [(f.current, 1.0)]
    if plan["share"] >= 1:
        return [(plan["alt"], 1.0)]
    return [(f.current, 1 - plan["share"]), (plan["alt"], plan["share"])]


def label_of(f, plan) -> str:
    parts = parts_of(f, plan)
    if len(parts) == 1:
        c = parts[0][0]
        return f"{nm(c)} 그대로" if c == f.current else f"{nm(c)}로 모두 바꾸기" if _no_final(nm(c)) else f"{nm(c)}으로 모두 바꾸기"
    return " + ".join(f"{nm(c)} {round(w * 100)}%" for c, w in parts)


def _no_final(word: str) -> bool:
    ch = word[-1]
    if not ("가" <= ch <= "힣"):
        return True
    jong = (ord(ch) - 0xAC00) % 28
    return jong in (0, 8)  # 받침 없음 또는 ㄹ받침 → '로'


def summer_crops(land: str) -> list[str]:
    return [c for c in E.crops()["작물"] if land in str(E.crop_row(c)["논밭"])
            and 3 <= int(str(E.crop_row(c)["파종시작"])[:2]) <= 7]


def field_from(d: dict):
    regions = [x["name"] for x in E.regions()]
    region = d.get("region", "합천")
    if region not in regions:
        raise InputError(f"지역을 다시 골라 주세요 ({region})")
    land = d.get("land", "논")
    if land not in ("논", "밭"):
        raise InputError("논이나 밭을 골라 주세요")
    water = d.get("water", "수혜구역")
    if water not in WATER:
        raise InputError("물 대는 방법을 다시 골라 주세요")
    drainage = d.get("drainage", "보통") if land == "논" else "좋음"
    if drainage not in LEVEL:
        raise InputError("물 빠짐을 다시 골라 주세요")
    labor = d.get("labor", "보통")
    if labor not in LABOR:
        raise InputError("일손을 다시 골라 주세요")
    current = d.get("current", "벼")
    if current not in summer_crops(land):
        w = nm(current)
        has_final = "가" <= w[-1] <= "힣" and (ord(w[-1]) - 0xAC00) % 28 != 0
        raise InputError(f"{w}{'은' if has_final else '는'} {land}에서 고를 수 없어요")
    prev = d.get("prev", "양파·마늘 거둔 뒤")
    if prev not in PREV:
        raise InputError("앞그루를 다시 골라 주세요")
    sales = d.get("sales", "공판장까지")
    if sales not in E.SALES_OK:
        raise InputError("판로를 다시 골라 주세요")
    area_py = num(d, "area_py", 3000, 100, 100000, "면적(평)")
    # 직불금 자격이 없는 작물(예: 2026년부터 백태는 전년도 이행 농가만) → 그 작물 직불금을 뺀다
    # 지금(또는 올해 심으려는) 작물이어도 적용한다: 올해 처음 논콩을 심는 농가도 2026년 백태 직불금을 못 받는다
    ns = d.get("no_subsidy") or []
    if not isinstance(ns, list) or not all(isinstance(c, str) for c in ns):
        raise InputError("직불금 자격은 작물 이름 목록으로 넣어 주세요")
    sub = {}
    for c in ns:
        if land == "논" and c in set(E.crops()["작물"]):  # 직불금은 논에서만 받음
            sub[c] = -float(E.crop_row(c)["직불_천원"])
    return E.Field(region=region, land=land, water=water, drainage=drainage, current=current,
                   free_from=PREV[prev], labor=labor, sales=sales, area_10a=area_py / 300, local_subsidy=sub)


def decision_of(d: dict, f) -> str:
    dec = d.get("decision")
    if dec:
        return mmdd_ok(dec, "작부를 정하는 날")
    return "06-01" if f.free_from == "06-10" else "04-01"


def excl_of(d: dict):
    return set(range(1992, 2006)) if d.get("recent") else None


def month_label(k: int) -> str:
    return f"{k % 12 + 1}월" if k < 12 else f"다음 해 {k % 12 + 1}월"


def r0(x) -> float:
    return float(round(float(x)))


def rn(x):
    """빈 값(NaN)일 수 있는 숫자: 비었으면 None (예: 1992년은 앞선 해가 없어 '평년 비'가 없음)."""
    x = float(x)
    return None if x != x else x


def last_weather_day(region: str) -> date:
    P = E.weather(region)[YEAR][0]
    ok = np.nonzero(~np.isnan(P))[0]
    d = E.NONLEAP[int(ok.max()) if len(ok) else 0]
    return date(YEAR, d.month, d.day)


# ---------------------------------------------------------------- 메타 (화면 선택지)
def meta(_: dict | None = None) -> dict:
    regs = [dict(name=x["name"], reservoir_obs=x["name"] in OBS_RESERVOIR) for x in E.regions()]
    def sow(c, land):
        g = E.Field(land=land, current=c, free_from="06-10" if land == "논" else "01-01")
        s, _ = E.plan_season(E.crop_row(c), g, E.doy("06-01" if land == "논" else "04-01"))
        return E.NONLEAP[s.sow].strftime("%m-%d") if s is not None else None

    return dict(regions=regs, crops={land: [dict(id=c, name=nm(c), sow=sow(c, land)) for c in summer_crops(land)] for land in ("논", "밭")},
                sales=list(E.SALES_OK), prev=list(PREV), weather_until=last_weather_day("합천").isoformat(), year=YEAR)


# ---------------------------------------------------------------- 손익 시뮬레이션 + 작물 추천
def _options(r, f):
    crops = list(r["results"])
    opts = [dict(plan="", alt=c, share=0.0 if c == f.current else 1.0) for c in crops]
    if f.current in r["results"]:
        for c in crops:
            if c != f.current:
                opts += [dict(plan="", alt=c, share=x) for x in (0.3, 0.5, 0.7)]
    return opts


def _option(r, f, plan, decision, k, money, living, need):
    _, L, net = C.plan_cases(r, f, plan, decision, with_price=True, cash_only=False)
    _, Lc, _ = C.plan_cases(r, f, plan, decision, with_price=True, cash_only=True)
    v = np.sort(net) * k
    n5, n20 = max(1, round(len(v) * 0.05)), max(1, round(len(v) * 0.2))
    Lm = Lc * k
    cum = Lm.cumsum(1)
    med, lo = np.median(cum, 0), np.percentile(cum, 10, 0)
    active = np.nonzero(np.abs(np.median(Lm, 0)) > 1e-6)[0]
    s0 = max(0, int(active.min()) - 1) if len(active) else 0
    months = list(range(s0, min(s0 + 12, cum.shape[1])))
    trough_m = int(months[int(np.argmin(med[months]))])
    rises = [m for m in months[1:] if med[m] - med[m - 1] > 1e-6]
    _, start, crop_end = fund_need(Lm, living, need)
    parts = C.plan_parts(r, f, plan)
    return dict(
        plan=dict(alt=plan["alt"], share=plan["share"]), label=label_of(f, plan),
        parts=[dict(crop=c, name=nm(c), share=w) for c, w in parts],
        mean=r0(v.mean()), mid=r0(np.median(v)), lo10=r0(np.percentile(v, 10)), hi90=r0(np.percentile(v, 90)),
        bad20=r0(v[:n20].mean()), worst5=r0(v[:n5].mean()), worst=r0(v[0]), loss_share=float((v < 0).mean()),
        score=r0(0.5 * v.mean() + 0.5 * v[:n20].mean()),
        labor_h=r0(sum(w * float(E.crop_row(c)["자가노동_h"]) for c, w in parts) * f.area_10a),
        need90=r0(np.percentile(start, 90)), survive=float((start <= money).mean()),
        crop_short=float((crop_end < need).mean()),
        trough=r0(med[trough_m]), trough_month=month_label(trough_m),
        first_pay_month=month_label(rises[0]) if rises else None,
        calendar=[dict(month=month_label(m), mid=r0(med[m]), lo10=r0(lo[m]), pay=m in rises) for m in months])


def _flips(f, decision, excl, base_label, alt):
    """답이 뒤집히는 조건: 조건을 하나씩 바꿔 엔진을 다시 돌린 균형 추천."""
    out = []
    crops = E.crops()

    def run(fx=None):
        g = fx or f
        p = E.compare(g, YEAR, decision, excl)["plan"]
        return label_of(g, p)

    def with_revenue(crop, mult, fx=None):
        i = crops.index[crops["작물"] == crop][0]
        base = float(crops.loc[i, "총수입_천원"])
        crops.loc[i, "총수입_천원"] = base * mult
        try:
            return run(fx)
        finally:
            crops.loc[i, "총수입_천원"] = base

    if alt and alt != f.current:
        out.append(dict(cond=f"{nm(alt)} 값이 5% 떨어지면", answer=with_revenue(alt, 0.95)))
        pay = float(E.crop_row(alt)["직불_천원"])
        if f.land == "논" and pay > 0:
            g = replace(f, local_subsidy={**f.local_subsidy, alt: -pay})
            out.append(dict(cond=f"처음 바꾸는 농가라 {nm(alt)} 직불금을 못 받으면", answer=run(g)))
    if f.current in set(crops["작물"]):
        seen, keep = base_label, label_of(f, dict(plan="", alt=f.current, share=0.0))
        if base_label != keep:  # 지금 작물을 그대로 두라는 답이 나올 때까지 1%씩 올려 본다
            for pct in range(1, 11):
                ans = with_revenue(f.current, 1 + pct / 100)
                if ans != seen:
                    out.append(dict(cond=f"{nm(f.current)} 판매수입이 {pct}% {'이상 ' if ans == keep else ''}높으면", answer=ans))
                    seen = ans
                if ans == keep:
                    break
        else:  # 지금 작물 그대로가 추천: 답이 바뀌는 가장 작은 변화를 이분 탐색으로 찾는다 (최대 30%)
            def first_change(crop, sign):
                lo, hi = 0, 30
                top = with_revenue(crop, 1 + sign * hi / 100)
                if top == base_label:
                    return None
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if with_revenue(crop, 1 + sign * mid / 100) == base_label:
                        lo = mid
                    else:
                        hi = mid
                return hi, with_revenue(crop, 1 + sign * hi / 100)

            hit = first_change(f.current, -1)
            out.append(dict(cond=f"{nm(f.current)} 판매수입이 {hit[0]}% 낮으면", answer=hit[1]) if hit
                       else dict(cond=f"{nm(f.current)} 판매수입이 30% 낮아도", answer=base_label))
            r0_ = E.compare(f, YEAR, decision, excl)["results"]
            others = [(c, E.score(v[2])[0]) for c, v in r0_.items() if c != f.current]
            if others:
                rival = max(others, key=lambda x: x[1])[0]
                hit = first_change(rival, +1)
                out.append(dict(cond=f"{nm(rival)} 값이 {hit[0]}% 높으면", answer=hit[1]) if hit
                           else dict(cond=f"{nm(rival)} 값이 30% 높아도", answer=base_label))
    for x in out:
        x["changed"] = x["answer"] != base_label
    return out


def calc(d: dict) -> dict:
    f = field_from(d)
    decision = decision_of(d, f)
    excl = excl_of(d)
    k = f.area_10a / 10
    money = num(d, "money", 1000, 0, 1_000_000, "가진 돈")
    living = num(d, "living", 100, 0, 10_000, "생활비")
    need = num(d, "need", 200, 0, 1_000_000, "남겨야 할 돈")
    try:
        r = E.compare(f, YEAR, decision, excl)
    except ValueError as e:
        raise InputError("이 날짜와 조건에서 심을 수 있는 작물이 없어요. 정하는 날을 앞당기거나 앞그루를 바꿔 보세요") from e
    opts = [_option(r, f, p, decision, k, money, living, need) for p in _options(r, f)]
    by_label = {o["label"]: o for o in opts}
    cur = next((o for o in opts if o["plan"]["share"] == 0), None)
    eng = r["plan"]
    bal_plan = eng if (eng["share"] > 0 or f.current in r["results"]) else dict(plan="", alt=eng["alt"], share=1.0)
    bal = by_label.get(label_of(f, bal_plan), max(opts, key=lambda o: o["score"]))
    best_mean = max(opts, key=lambda o: o["mean"])
    best_safe = max(opts, key=lambda o: o["worst5"])
    easy_pool = [o for o in opts if o["mean"] >= 0.6 * best_mean["mean"]] or opts
    best_easy = min(easy_pool, key=lambda o: (o["labor_h"], -o["mean"]))

    climate = None
    if f.current in r["results"]:
        _, sims, _ = r["results"][f.current]
        climate = dict(years=len(sims), dry=sum(1 for s in sims if s["water_ratio"] < 0.9),
                       wet=sum(1 for s in sims if s["wet_events"] > 0))
    be = r["breakeven"]
    breakeven = None
    if cur is not None and not be.empty and bal_plan["alt"] != f.current:
        # 추천에 섞인 작물로 '모두' 바꾸려면 지원금이 얼마나 더 있어야 하는가 (이미 앞서면 보이지 않음)
        b = be[(be["대안"] == bal_plan["alt"]) & (be["점수차_천원"] > 0)].head(1)
        if not b.empty:
            b = b.iloc[0]
            p = b["현재작물가격_변화필요_퍼센트"]
            breakeven = dict(alt=nm(b["대안"]), subsidy_gap=r0(float(b["점수차_천원"]) * k),
                             price_change=None if p is None or p != p else float(p))
    st = r["state"]
    ranked = sorted(opts, key=lambda o: -o["score"])
    return dict(
        input=dict(region=f.region, land=f.land, water=f.water, drainage=f.drainage, current=f.current,
                   current_name=nm(f.current), labor=f.labor, area_py=round(f.area_10a * 300), decision=decision,
                   money=money, living=living, need=need, recent=bool(excl), pump=d.get("pump", "일반"),
                   rev_pct=d.get("rev_pct") or {}, no_subsidy=sorted(f.local_subsidy), pay_crop=d.get("pay_crop"),
                   pay_mode=d.get("pay_mode", "default")),
        state=dict(reservoir_rate=st.get("reservoir_rate"), reservoir_source=st.get("reservoir_source", "계산"),
                   state=st.get("state")),
        reservoir_obs=f.region in OBS_RESERVOIR,
        current=cur, balanced=bal, best_mean=best_mean, best_safe=best_safe, best_easy=best_easy,
        options=ranked, climate=climate, breakeven=breakeven,
        pay_options={c: pay_options(c) for c in r["results"]},
        excluded=[dict(crop=nm(x["작물"]), why=x["이유"]) for _, x in r["excluded"].iterrows()] if len(r["excluded"]) else [],
        cases=int(len(r["analog_years"]) * len(E.ASSUME["price_z"])), years=[int(y) for y in r["analog_years"]])


def flips(d: dict) -> dict:
    """답이 뒤집히는 조건 (엔진을 여러 번 다시 돌려서 calc 와 따로 부른다)."""
    f = field_from(d)
    decision = decision_of(d, f)
    excl = excl_of(d)
    try:
        r = E.compare(f, YEAR, decision, excl)
    except ValueError as e:
        raise InputError("이 조건에서 심을 수 있는 작물이 없어요") from e
    eng = r["plan"]
    bal_plan = eng if (eng["share"] > 0 or f.current in r["results"]) else dict(plan="", alt=eng["alt"], share=1.0)
    base = label_of(f, bal_plan)
    return dict(base=base, flips=_flips(f, decision, excl, base, bal_plan["alt"]))


# ---------------------------------------------------------------- 농사 중 다시 계산하기 (내 농장)
def farm(d: dict) -> dict:
    f = field_from(d)
    decision = decision_of(d, f)
    excl = excl_of(d)
    k = f.area_10a / 10
    year = int(num(d, "year", YEAR, 1992, YEAR, "연도"))
    if not 1992 <= year <= YEAR:
        raise InputError("연도는 1992~2026년 사이로 골라 주세요")
    if d.get("plan") == "balanced":  # 첫 화면: calc 를 기다리지 않고 균형 추천을 여기서 바로 고른다
        try:
            rb = E.compare(f, YEAR, decision, excl)
        except ValueError as e:
            raise InputError("이 날짜와 조건에서 심을 수 있는 작물이 없어요") from e
        p = rb["plan"]
        alt, share = p["alt"], (p["share"] if f.current in rb["results"] else 1.0)
    else:
        alt = d.get("alt") or f.current
        if alt not in summer_crops(f.land):
            raise InputError("심은 작물을 다시 골라 주세요")
        share = num(d, "share", 0.0 if alt == f.current else 1.0, 0, 1, "섞는 비율")
    plan = dict(plan="", alt=alt, share=share)
    sown = d.get("sown")
    if sown is not None:
        if not isinstance(sown, dict):
            raise InputError("심은 날은 {작물: 'MM-DD'} 형식으로 넣어 주세요")
        for c, v in sown.items():
            if c not in summer_crops(f.land):
                raise InputError("심은 날을 넣은 작물을 다시 골라 주세요")
            mmdd_ok(v, f"{nm(c)} 심은 날")
    try:
        fs = R.with_sown(f, plan, decision)  # 안에 든 작물의 기본 심는 날
    except ValueError as e:
        raise InputError(f"이 날짜에 심을 수 없어요: {e}") from e
    if sown:  # 직접 넣은 심은 날로 바꾼다 (안에 없는 작물은 무시)
        fs = replace(fs, sown={c: sown.get(c, v) for c, v in fs.sown.items()})
    last = last_weather_day(f.region) if year == YEAR else date(year, 12, 31)
    first = min(E.doy(x) for x in fs.sown.values())
    harvest = max(E.doy(x) + int(E.crop_row(c)["생육일수"]) for c, x in fs.sown.items())
    limit = min(E.doy(last.strftime("%m-%d")), harvest, 364)
    today = mmdd_ok(d["today"], "기준일") if d.get("today") else R.mmdd(limit)
    if E.doy(today) > limit:
        today = R.mmdd(limit)
    end = E.doy(today)
    days = sorted(set(list(range(first, end, 15)) + [first, end])) if end > first else [first]
    path, so_far = [], {}
    for day in days:
        st_, sf = R.outlook(fs, year, plan, R.mmdd(day), excl)
        path.append(dict(date=R.mmdd(day), mid=r0(st_["보통해"] * k), lo10=r0(st_["하위10"] * k), hi90=r0(st_["상위10"] * k),
                         bad20=r0(st_["나쁜20"] * k)))
        so_far = sf
    crops_now = []
    for crop, p in so_far.items():
        x = dict(crop=crop, name=nm(crop), sown=fs.sown[crop], days=int(p.get("지난날수", 0)), length=int(p.get("생육일수", 0)),
                 progress=float(p.get("진행률", 0.0)))
        if "비" in p:
            x.update(rain=r0(p["비"]), normal_rain=None if rn(p["평년비"]) is None else r0(p["평년비"]), rain_rank=rn(p["비순위"]),
                     heavy_rain=int(p.get("큰비횟수", 0)), water_ok=float(p.get("물충족률", 1.0)))
        crops_now.append(x)
    actual = None
    if year < YEAR:  # 지난 해: 그해 실제 날씨로 끝까지 지었을 때(평소 가격)
        a = R.actual(fs, year, plan, decision)
        actual = None if a is None else r0(a * k)
    return dict(label=label_of(f, plan), year=year, today=today, weather_until=last.isoformat(), path=path, crops=crops_now,
                first=path[0], now=path[-1], actual=actual, area_py=round(f.area_10a * 300))


# ---------------------------------------------------------------- 재해 뒤 비교
def _stat(x, k):
    v = np.sort(np.asarray(x, float).ravel()) * k
    return dict(mid=r0(np.median(v)), lo10=r0(np.percentile(v, 10)), mean=r0(v.mean()))


def disaster(d: dict) -> dict:
    f = field_from(d)
    k = f.area_10a / 10
    crop = d.get("crop") or f.current
    if crop not in summer_crops(f.land):
        raise InputError("피해 입은 작물을 다시 골라 주세요")
    year = int(num(d, "year", YEAR, 1992, YEAR, "연도"))
    if not 1992 <= year <= YEAR:
        raise InputError("연도는 1992~2026년 사이로 골라 주세요")
    sown, hit = mmdd_ok(d.get("sown", "06-10"), "심은 날"), mmdd_ok(d.get("hit", "07-20"), "재해 난 날")
    if year == YEAR and E.doy(hit) > E.doy(last_weather_day(f.region).strftime("%m-%d")):
        raise InputError(f"재해 난 날은 날씨 자료가 있는 {last_weather_day(f.region).month}월 {last_weather_day(f.region).day}일까지 넣을 수 있어요")
    if E.doy(hit) <= E.doy(sown):
        raise InputError("재해 난 날은 심은 날 뒤여야 해요")
    cost0 = float(E.crop_row(crop)["경영비_천원"])
    fc = num(d, "fix_cost", 0, 0, 1_000_000, "되살리는 비용", allow_none=True)
    fix_cost = fc / k if fc is not None else 0.1 * cost0
    fix_share = num(d, "fix_share", 0.3, 0, 1, "되살릴 수 있는 몫")
    fix_sup = num(d, "fix_support", 0, 0, 1_000_000, "농약대 등 지원") / k
    rep_sup = num(d, "replant_support", 0, 0, 1_000_000, "대파대 등 지원") / k
    dmg = num(d, "damage", 0, 0, 1, "피해율", allow_none=True)
    fs = replace(f, sown={crop: sown})
    try:
        r = E.after_disaster(fs, year, crop, hit, None if dmg is None else float(dmg), fix_cost, fix_share, fix_sup, rep_sup,
                             exclude_years=excl_of(d))
    except ValueError as e:
        raise InputError(f"이 조건으로는 계산할 수 없어요: {e}") from e
    opts = [dict(name="그대로 두기", **_stat(r["keep"], k)), dict(name="되살리기", **_stat(r["repair"], k)),
            dict(name="갈아엎고 비워 두기", **_stat(r["abandon"], k))]
    for c, v in r["replant"].items():
        opts.append(dict(name=f"{nm(c)} 다시 심기", sow=r["replant_info"][c]["파종일"], **_stat(v, k)))
    best = max(opts, key=lambda o: o["mid"])
    return dict(crop=nm(crop), year=year, sown=sown, hit=hit, model_damage=float(r["model_damage"]), damage=float(r["damage"]),
                sunk=r0(r["sunk"] * k), fix_cost=r0(fix_cost * k), fix_share=fix_share,
                heavy_rain=int(r["so_far"].get("큰비횟수", 0)), options=opts, best=best["name"],
                next_year=[nm(c) for c in r["next_year"]], area_py=round(f.area_10a * 300))


# ---------------------------------------------------------------- 배수 공사의 값어치 (analysis/drainage.py 와 같은 계산)
def drainage(d: dict) -> dict:
    f = field_from(d)
    if f.land != "논":
        raise InputError("배수 공사 계산은 논에서만 해요")
    decision = decision_of(d, f)
    excl = excl_of(d)
    k = f.area_10a / 10
    c_in = num(d, "cost", 0, 0, 10_000_000, "공사비", allow_none=True)
    cost = c_in if c_in is not None else 650.0 * k  # 무굴착 암거 ha당 650만 원(연구 시험 값)
    support = num(d, "support", 0, 0, 100, "지원받는 몫") / 100
    own = cost * (1 - support)
    rows = []
    for lv in ("나쁨", "보통", "좋음"):
        g = replace(f, drainage=lv)
        r = E.compare(g, YEAR, decision, excl)
        row = dict(level=lv)
        if f.current in r["results"]:
            _, mean, bad = E.score(r["results"][f.current][2])
            row.update(cur_mean=r0(mean * k), cur_bad20=r0(bad * k))
        p = r["plan"]
        pp = p if (p["share"] > 0 or f.current in r["results"]) else dict(plan="", alt=p["alt"], share=1.0)
        row.update(bal_label=label_of(g, pp), bal_mean=r0(p["mean"] * k), bal_bad20=r0(p["bad"] * k))
        rows.append(row)
    base = next(x for x in rows if x["level"] == f.drainage)
    for x in rows:
        for key in ("cur", "bal"):
            if f"{key}_mean" in x and f"{key}_mean" in base:
                gain = x[f"{key}_mean"] - base[f"{key}_mean"]
                x[f"{key}_gain"] = r0(gain)
                # 한 해 5만 원(3,000평 기준)도 안 늘면 '되찾지 못함' (drainage.payback 과 같은 기준)
                x[f"{key}_payback"] = None if gain < 5 * k else round(own / gain, 1)
    return dict(levels=rows, now=f.drainage, cost=r0(cost), own=r0(own), support=support, current_name=nm(f.current),
                area_py=round(f.area_10a * 300))


# ---------------------------------------------------------------- 기후 위기 (analysis/climate_reco.py, recent_climate.py 와 같은 계산)
def _by_year(res, crop):
    _, sims, pr = res[crop]
    return {s["analog"]: (float(pr[i].mean()), float(s["season_wb"])) for i, s in enumerate(sims)}


def _yearly_stats(v: np.ndarray, k: float) -> dict:
    """해마다 손익(가격 5가지 평균) 34개로 본 평균·흔들림·나쁜 20%(기획안 결과 3 기준)."""
    s = np.sort(v)
    n = max(1, round(len(s) * 0.2))
    return dict(mean=r0(s.mean() * k), std=r0(s.std(ddof=1) * k),  # 표본 표준편차 (기획안 표와 같음)
                bad20=r0(s[:n].mean() * k), worst=r0(s[0] * k),
                loss_years=int((s < 0).sum()))


def climate(d: dict) -> dict:
    f = field_from(d)
    decision = decision_of(d, f)
    excl = excl_of(d)
    k = f.area_10a / 10
    r = E.compare(f, YEAR, decision, excl)
    res = r["results"]
    out = dict(region=f.region, current_name=nm(f.current), area_py=round(f.area_10a * 300))

    # 1) 가장 가물었던 20%·비가 가장 많았던 20% 해의 손익: 지금 작물만 / 대안만 / 반반
    alt = d.get("alt")
    if not alt or alt not in res or alt == f.current:
        p = r["plan"]
        alt = p["alt"] if p["alt"] != f.current and p["alt"] in res else None
        if alt is None:
            others = [(c, E.score(v[2])[0]) for c, v in res.items() if c != f.current]
            alt = max(others, key=lambda x: x[1])[0] if others else None
    if f.current in res and alt:
        a, b = _by_year(res, f.current), _by_year(res, alt)
        years = sorted(set(a) & set(b), key=lambda y: a[y][1])  # 지금 작물 작기의 물수지(비 − 증발) 순
        n = max(1, round(len(years) * 0.2))
        dry, wet = years[:n], years[-n:]
        plans = [(f"{nm(f.current)}만", lambda y: a[y][0]), (f"{nm(alt)}만", lambda y: b[y][0]),
                 ("반반 섞기", lambda y: 0.5 * a[y][0] + 0.5 * b[y][0])]
        rows = []
        for name, fn in plans:
            v = np.array([fn(y) for y in years])
            rows.append(dict(name=name, dry=r0(np.mean([fn(y) for y in dry]) * k), wet=r0(np.mean([fn(y) for y in wet]) * k),
                             **_yearly_stats(v, k)))
        mix = rows[2]
        out["hedge"] = dict(alt=alt, alt_name=nm(alt), rows=rows, dry_years=sorted(dry), wet_years=sorted(wet), n=n,
                            years=len(years),
                            std_cut=[round(1 - mix["std"] / x["std"], 3) if x["std"] else None for x in rows[:2]],
                            bad_gain=[r0(mix["bad20"] - x["bad20"]) for x in rows[:2]],
                            alts=[dict(id=c, name=nm(c)) for c in res if c != f.current])

    # 2) 큰비가 잦아지나: 작기(6~9월)에 3일 100mm 넘는 비가 온 해의 비율, 34년 전체 vs 최근 15년
    W = E.weather(f.region)

    def big_share(y0):
        ys = [y for y in range(y0, 2026) if y in W]
        hit = [bool((np.convolve(np.nan_to_num(W[y][0][151:273]), np.ones(3), "valid") >= E.ASSUME["wet_rain_3d"]).any()) for y in ys]
        return float(np.mean(hit)), len(ys)

    all_s, all_n = big_share(1992)
    rec_s, rec_n = big_share(2011)
    trend = dict(all=all_s, all_years=all_n, recent=rec_s, recent_years=rec_n)
    if f.current in res:
        r15 = E.compare(f, YEAR, decision, set(range(1992, 2011)))
        if f.current in r15["results"]:
            trend.update(cur_all=r0(E.score(res[f.current][2])[1] * k), cur_recent=r0(E.score(r15["results"][f.current][2])[1] * k))
    out["trend"] = trend

    # 3) 가뭄 위험은 어떤 땅에 몰리나: 같은 지역, 땅마다 34년 중 물이 모자라 수확이 10% 넘게 준 해
    lands = [("저수지 논 (벼)", dict(land="논", water="수혜구역", current="벼"), "일반"),
             ("관정 논 (벼)", dict(land="논", water="관정", current="벼"), "일반"),
             ("작은 관정 논 (벼, 하루 5mm)", dict(land="논", water="관정", current="벼"), "작은"),
             ("빗물 논 (논콩)", dict(land="논", water="없음", current="콩(논 재배)"), "일반"),
             ("물 없는 밭 (참깨)", dict(land="밭", water="없음", current="참깨"), "일반")]
    saved_pump = E.ASSUME["pump_mm_per_day"]
    drought = []
    try:
        for label, kw, pump in lands:
            E.ASSUME["pump_mm_per_day"] = PUMP[pump]
            g = E.Field(region=f.region, drainage="보통" if kw["land"] == "논" else "좋음", labor=f.labor, sales=f.sales,
                        free_from="06-10" if kw["land"] == "논" else "01-01", **kw)
            try:
                rr = E.compare(g, YEAR, "06-01" if kw["land"] == "논" else "04-01", excl)
            except ValueError:
                continue
            if g.current in rr["results"]:
                sims = rr["results"][g.current][1]
                drought.append(dict(land=label, dry=sum(1 for s in sims if s["water_ratio"] < 0.9), years=len(sims)))
    finally:
        E.ASSUME["pump_mm_per_day"] = saved_pump
    out["drought"] = drought

    # 4) 물과 전기: 관정으로 물을 대는 같은 땅에서 지금 작물 vs 대안 작물의 한 해 양수량
    if f.land == "논" and alt:
        g = replace(f, water="관정")
        try:
            rw = E.compare(g, YEAR, decision, excl)["results"]
        except ValueError:
            rw = {}
        if f.current in rw and alt in rw:
            mm_cur = float(np.mean([s["irrigation_mm"] for s in rw[f.current][1]]))
            mm_alt = float(np.mean([s["irrigation_mm"] for s in rw[alt][1]]))
            tons = (mm_cur - mm_alt) * f.area_10a  # 1mm × 10a = 1m³
            out["water"] = dict(cur_mm=r0(mm_cur), alt_mm=r0(mm_alt), tons=r0(tons), kwh=r0(tons * E.ASSUME["kwh_per_m3"]),
                                kwh_per_m3=E.ASSUME["kwh_per_m3"], alt_name=nm(alt))
    return out


# ---------------------------------------------------------------- 땅마다 다른 답: 논 9가지 (analysis/screening.py 와 같은 계산)
def static_best(f, decision: str) -> str:
    """직불금을 더한 평균 소득 자료 1위 (analysis/validate.static_best 와 같음)."""
    best, val = None, -1e9
    for _, row in E.crops().iterrows():
        s, _ = E.plan_season(row, f, E.doy(decision))
        if s is None:
            continue
        v = row["소득_천원"] + (row["직불_천원"] if f.land == "논" else 0) \
            - row["자가노동_h"] * E.ASSUME["labor_hire_share"][f.labor] * E.ASSUME["wage"]
        if v > val:
            best, val = row["작물"], v
    return best


def grid(d: dict) -> dict:
    base = field_from({**d, "land": "논", "current": "벼"})
    decision = decision_of(d, base)
    excl = excl_of(d)
    k = base.area_10a / 10
    cells = []
    for w in ("수혜구역", "관정", "없음"):
        for dr in ("좋음", "보통", "나쁨"):
            f = replace(base, water=w, drainage=dr)
            c = E.compare(f, YEAR, decision, excl)
            p = c["plan"]
            if f.current in c["results"]:
                ans = label_of(f, p)
            else:
                ans = nm(p["alt"])
            sb = static_best(f, decision)
            cell = dict(water=w, drainage=dr, answer=ans, rice_ok=f.current in c["results"],
                        alt=nm(p["alt"]), share=p["share"], stat_best=nm(sb), same=p["alt"] == sb)
            for crop, key in (("벼", "rice"), ("콩(논 재배)", "soy")):
                if crop in c["results"]:
                    _, mean, bad = E.score(c["results"][crop][2])
                    cell[f"{key}_mean"], cell[f"{key}_bad20"] = r0(mean * k), r0(bad * k)
            cells.append(cell)
    return dict(region=base.region, cells=cells, area_py=round(base.area_10a * 300))


def _wrap(fn):
    def run(d: dict) -> dict:
        with scenario(d):
            return fn(d)
    return run


ROUTES = {"meta": meta, **{n: _wrap(fn) for n, fn in dict(calc=calc, flips=flips, farm=farm, disaster=disaster,
                                                           drainage=drainage, climate=climate, grid=grid).items()}}
