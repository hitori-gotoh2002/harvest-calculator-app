"""수확계산기 계산 서비스: 화면 입력 → 엔진 → 화면에 쓸 숫자.

- 엔진(analysis/engine.py, cashflow.py, recheck.py)은 분석 저장소(multtae_handoff/analysis)와 같은 파일을 그대로 쓴다.
  숫자가 기획안과 같게 나오도록 엔진은 고치지 않는다. 고칠 일이 있으면 분석 저장소에서 고친 뒤 복사한다.
- 엔진 금액 단위는 천 원/10a. 화면 금액은 입력한 면적 기준 만 원(= 천 원/10a × 면적(10a) ÷ 10).
- '경우' = 34개 날씨 해 × 가격 5가지(170가지). 비율은 확률이 아니라 경우 중 비율.
"""
from __future__ import annotations

import sys
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


class InputError(ValueError):
    """화면에 그대로 보여 줄 수 있는 입력 오류."""


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
    area_py = float(d.get("area_py", 3000))
    if not 100 <= area_py <= 100000:
        raise InputError("면적은 100~100,000평 사이로 넣어 주세요")
    return E.Field(region=region, land=land, water=water, drainage=drainage, current=current,
                   free_from=PREV[prev], labor=labor, sales=sales, area_10a=area_py / 300)


def decision_of(d: dict, f) -> str:
    dec = d.get("decision")
    if dec:
        try:
            date(YEAR, int(dec[:2]), int(dec[3:5]))
        except (ValueError, TypeError):
            raise InputError("작부를 정하는 날을 다시 넣어 주세요 (예: 06-01)")
        return dec
    return "06-01" if f.free_from == "06-10" else "04-01"


def excl_of(d: dict):
    return set(range(1992, 2006)) if d.get("recent") else None


def month_label(k: int) -> str:
    return f"{k % 12 + 1}월" if k < 12 else f"다음 해 {k % 12 + 1}월"


def r0(x) -> float:
    return float(round(float(x)))


def last_weather_day(region: str) -> date:
    P = E.weather(region)[YEAR][0]
    ok = np.nonzero(~np.isnan(P))[0]
    d = E.NONLEAP[int(ok.max()) if len(ok) else 0]
    return date(YEAR, d.month, d.day)


# ---------------------------------------------------------------- 메타 (화면 선택지)
def meta(_: dict | None = None) -> dict:
    regs = [dict(name=x["name"], reservoir_obs=x["name"] in OBS_RESERVOIR) for x in E.regions()]
    return dict(regions=regs, crops={land: [dict(id=c, name=nm(c)) for c in summer_crops(land)] for land in ("논", "밭")},
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
    for x in out:
        x["changed"] = x["answer"] != base_label
    return out


def calc(d: dict) -> dict:
    f = field_from(d)
    decision = decision_of(d, f)
    excl = excl_of(d)
    k = f.area_10a / 10
    money = float(d.get("money", 1000))
    living = float(d.get("living", 100))
    need = float(d.get("need", 200))
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
                   money=money, living=living, need=need, recent=bool(excl)),
        state=dict(reservoir_rate=st.get("reservoir_rate"), reservoir_source=st.get("reservoir_source", "계산"),
                   state=st.get("state")),
        reservoir_obs=f.region in OBS_RESERVOIR,
        current=cur, balanced=bal, best_mean=best_mean, best_safe=best_safe, best_easy=best_easy,
        options=ranked, climate=climate, breakeven=breakeven,
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
    year = int(d.get("year", YEAR))
    if not 1992 <= year <= YEAR:
        raise InputError("연도는 1992~2026년 사이로 골라 주세요")
    alt = d.get("alt") or f.current
    share = float(d.get("share", 0.0 if alt == f.current else 1.0))
    plan = dict(plan="", alt=alt, share=share)
    sown = d.get("sown")
    try:
        fs = replace(f, sown=sown) if sown else R.with_sown(f, plan, decision)
    except ValueError as e:
        raise InputError(f"이 날짜에 심을 수 없어요: {e}") from e
    last = last_weather_day(f.region) if year == YEAR else date(year, 12, 31)
    first = min(E.doy(x) for x in fs.sown.values())
    harvest = max(E.doy(x) + int(E.crop_row(c)["생육일수"]) for c, x in fs.sown.items())
    limit = min(E.doy(last.strftime("%m-%d")), harvest, 364)
    today = d.get("today") or R.mmdd(limit)
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
            x.update(rain=r0(p["비"]), normal_rain=r0(p["평년비"]), rain_rank=float(p["비순위"]),
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
    year = int(d.get("year", YEAR))
    if not 1992 <= year <= YEAR:
        raise InputError("연도는 1992~2026년 사이로 골라 주세요")
    sown, hit = d.get("sown", "06-10"), d.get("hit", "07-20")
    if year == YEAR and E.doy(hit) > E.doy(last_weather_day(f.region).strftime("%m-%d")):
        raise InputError(f"재해 난 날은 날씨 자료가 있는 {last_weather_day(f.region):%m월 %d일}까지 넣을 수 있어요")
    if E.doy(hit) <= E.doy(sown):
        raise InputError("재해 난 날은 심은 날 뒤여야 해요")
    dmg = d.get("damage")
    cost0 = float(E.crop_row(crop)["경영비_천원"])
    fix_cost = float(d["fix_cost"]) / k if d.get("fix_cost") is not None else 0.1 * cost0
    fix_share = float(d.get("fix_share", 0.3))
    fix_sup = float(d.get("fix_support", 0)) / k
    rep_sup = float(d.get("replant_support", 0)) / k
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


ROUTES = {"meta": meta, "calc": calc, "flips": flips, "farm": farm, "disaster": disaster}
