"""농사 중 다시 계산하기 (기획서 '본선 준비' 단계, 2026-11-21).

심을 때 본 전망을, 심은 뒤 날짜가 지날 때마다 '그날까지의 올해 실제 날씨 + 그 뒤는 지난 34개 해 날씨'로
다시 계산한다. 앞으로의 날씨를 맞히지 않는다. 지나간 날의 비·가뭄은 실제 값으로 바뀌므로 범위가 줄고 옮겨 간다.

- 금액: 3,000평(1ha) 기준 만 원 (엔진의 천 원/10a 값과 숫자가 같다).
- 손익은 감가상각을 넣은 기준(기획서 대표 사례 표의 '한 해 평균·나쁜 해'와 같은 기준).
- 2026년 실측 저수율은 아직 없어 저수지는 날씨로 계산한다. 가격·기타 재해는 이어 붙인 해의 값을 쓴다.

실행: python analysis/recheck.py → data/processed/recheck_2026.csv, recheck_2026_path.csv,
      recheck_demo_path.csv, submission/build/recheck_demo.png(발표·보완 기획안 그림),
      disaster_demo.csv(재해 뒤 세 가지 비교)
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cashflow as C  # noqa: E402
import engine as E  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"


def mmdd(d: int) -> str:
    return E.NONLEAP[int(d)].strftime("%m-%d")


def with_sown(f: E.Field, plan: dict, decision: str) -> E.Field:
    """계획에 든 작물을 decision 기준 파종일에 심었다고 적은 땅 정보."""
    parts = [(f.current, 1.0)] if plan["share"] <= 0 else (
        [(plan["alt"], 1.0)] if plan["share"] >= 1 else [(f.current, 1 - plan["share"]), (plan["alt"], plan["share"])])
    sown = {}
    for crop, _ in parts:
        season, why = E.plan_season(E.crop_row(crop), replace(f, sown={}), E.doy(decision))
        if season is None:
            raise ValueError(f"{crop}: {why}")
        sown[crop] = mmdd(season.sow)
    return replace(f, sown=sown)


def stats(net: np.ndarray) -> dict:
    v = np.sort(np.asarray(net, float).ravel())
    n20, n5 = max(1, round(len(v) * 0.2)), max(1, round(len(v) * 0.05))
    return dict(평균=v.mean(), 하위10=np.percentile(v, 10), 보통해=np.median(v), 상위10=np.percentile(v, 90),
                나쁜20=v[:n20].mean(), 최악5=v[:n5].mean(), 적자비율=(v < 0).mean(), 경우=len(v))


def outlook(fs: E.Field, year: int, plan: dict, today: str, exclude_years=None) -> tuple[dict, dict]:
    """fs(심은 날이 적힌 땅)의 today 기준 전망 통계와 작물별 '지금까지' 기록."""
    r = E.recheck(fs, year, today, exclude_years)
    _, _, net = C.plan_cases(r, fs, plan, today, with_price=True, cash_only=False)
    return stats(net), r["so_far"]


def actual(fs: E.Field, year: int, plan: dict, decision: str) -> float | None:
    """그해 실제 날씨로 끝까지 지었을 때 손익(가격은 그해 값이 있으면 그 값, 없으면 기준값)."""
    tot = 0.0
    for crop, w in C.plan_parts(dict(results=dict.fromkeys(fs.sown)), fs, plan):
        v = E.realized(fs, year, decision, crop)
        if v is None:
            return None
        tot += w * v
    return tot


def path(f: E.Field, year: int, plan: dict, decision: str, step: int = 15, last: str | None = None) -> pd.DataFrame:
    """심는 날부터 수확까지 step 일마다 다시 계산한 전망."""
    fs = with_sown(f, plan, decision)
    sow = min(E.doy(d) for d in fs.sown.values())
    end = max(E.doy(d) + int(E.crop_row(c)["생육일수"]) for c, d in fs.sown.items())
    stop = min(end, E.doy(last)) if last else end
    days = list(range(sow, stop, step)) + [stop]
    rows = []
    for d in days:
        st, sf = outlook(fs, year, plan, mmdd(d))
        row = dict(기준날짜=mmdd(d), **{k: v for k, v in st.items()})
        for crop, p in sf.items():
            for k in ("진행률", "비", "평년비", "큰비횟수", "물충족률"):
                if k in p:
                    row[f"{crop}_{k}"] = p[k]
        rows.append(row)
    return pd.DataFrame(rows)


def six_types(TYPES, year=2026):
    """여섯 가지 땅 유형: 지금 작물 그대로 / 균형 추천을 심은 뒤 날짜별 전망."""
    out, paths = [], []
    for name, (f, decs) in TYPES.items():
        dec = decs[1]
        bal = E.compare(f, year, dec)["plan"]
        plans = {"지금 작물 그대로": dict(plan="", alt=f.current, share=0.0)}
        if bal["share"] > 0:
            plans[f"균형 추천({bal['plan']})"] = dict(plan="", alt=bal["alt"], share=bal["share"])
        for pname, plan in plans.items():
            try:
                p = path(f, year, plan, dec)
            except ValueError as e:
                print(name, pname, "계산 불가:", e)
                continue
            fs = with_sown(f, plan, dec)
            act = actual(fs, year, plan, dec)
            p.insert(0, "계획", pname)
            p.insert(0, "땅", name)
            paths.append(p)
            first, lastrow = p.iloc[0], p.iloc[-1]
            out.append(dict(땅=name, 계획=pname, 심은날=", ".join(f"{c} {d}" for c, d in fs.sown.items()),
                            심을때_보통해=first["보통해"], 심을때_하위10=first["하위10"], 심을때_적자비율=first["적자비율"],
                            마지막_기준날짜=lastrow["기준날짜"], 마지막_보통해=lastrow["보통해"], 마지막_하위10=lastrow["하위10"],
                            그해실제날씨_손익=act))
            show = p[["기준날짜", "평균", "하위10", "보통해", "상위10", "적자비율"]].copy()
            show["적자비율"] = show["적자비율"] * 100  # %
            print(f"{name} | {pname} | 심은 날 {fs.sown}")
            print(show.round(0).to_string(index=False))
            print("  그해 실제 날씨로 끝까지:", None if act is None else round(act))
    pd.DataFrame(out).round(3).to_csv(OUT / f"recheck_{year}.csv", index=False, encoding="utf-8-sig")
    pd.concat(paths).round(3).to_csv(OUT / f"recheck_{year}_path.csv", index=False, encoding="utf-8-sig")


DEMOS = [  # (제목, 땅 유형, 계획, 연도)
    ("대표 사례: 합천 저수지 논, 벼 50% + 논콩 50% (2026년)", "A 수혜구역 논(벼)", dict(plan="", alt="콩(논 재배)", share=0.5), 2026),
    ("물 빠짐 나쁜 논, 논콩 그대로 (2020년 긴 장마로 연습)", "D 배수 나쁜 논(콩)", dict(plan="", alt="콩(논 재배)", share=0.0), 2020),
]


def demos(TYPES):
    """발표·보완 기획안용 두 사례: 날짜별 전망 + 그해 실제 날씨로 끝까지 지은 값 + 그림."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    BLUE, ORANGE, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df"

    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, (title, key, plan, year) in zip(axes, DEMOS):
        f, decs = TYPES[key]
        dec = decs[1]
        p = path(f, year, plan, dec)
        fs = with_sown(f, plan, dec)
        act = actual(fs, year, plan, dec)
        p.insert(0, "연도", year)
        p.insert(0, "사례", title)
        p["그해실제날씨_손익"] = act
        rows.append(p)
        x = pd.to_datetime([f"{year}-{d}" for d in p["기준날짜"]])
        ax.fill_between(x, p["하위10"], p["상위10"], color=BLUE, alpha=0.2, lw=0)
        ax.plot(x, p["보통해"], color=BLUE, lw=2, marker="o", ms=4)
        if act is not None:
            ax.axhline(act, color=ORANGE, ls="--", lw=1.6)
            ax.annotate(f"그해 실제 날씨로 끝까지 {act:,.0f}", (x[-1], act), xytext=(0, 6), textcoords="offset points",
                        ha="right", fontsize=9, color=ORANGE)
        if p["하위10"].min() < 0:
            ax.axhline(0, color=INK2, lw=0.8, ls=":")
        ax.annotate(f"심을 때 보통 해 {p['보통해'].iloc[0]:,.0f}", (x[0], p["보통해"].iloc[0]), xytext=(4, 8),
                    textcoords="offset points", fontsize=9, color=INK)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(axis="y", color=GRID, lw=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=9)
        print(title)
        show = p[["기준날짜", "하위10", "보통해", "상위10", "적자비율"]].copy()
        show["적자비율"] = show["적자비율"] * 100
        print(show.round(0).to_string(index=False), "\n  그해 실제 날씨로 끝까지:", None if act is None else round(act))
    axes[0].set_ylabel("한 해 손익 (만 원, 3,000평)", color=INK2, fontsize=9.5)
    fig.text(0.01, 0.01, "띠: 나쁜 쪽 10%~좋은 쪽 10%   선: 보통 해   점: 그날까지 실제 날씨를 넣어 다시 계산(15일 간격)   "
             "주황 점선: 그해 실제 날씨로 끝까지(그날에는 알 수 없던 값)", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(ROOT / "submission" / "build" / "recheck_demo.png", dpi=200)
    plt.close(fig)
    pd.concat(rows).round(3).to_csv(OUT / "recheck_demo_path.csv", index=False, encoding="utf-8-sig")


DISASTERS = [  # (제목, 땅 유형, 작물, 심은 날, 연도, 재해 난 날) — 2020년 7월 11~13일·8월 6~8일 합천 큰비
    ("물 빠짐 나쁜 논 논콩, 2020년 7월 첫 큰비 뒤", "D 배수 나쁜 논(콩)", "콩(논 재배)", "06-15", 2020, "07-14"),
    ("물 빠짐 나쁜 논 논콩, 2020년 8월 큰비 뒤", "D 배수 나쁜 논(콩)", "콩(논 재배)", "06-15", 2020, "08-09"),
]


def disaster_demo(TYPES):
    """재해 뒤 세 가지 안(피해율 = 모형 값, 되살리기 = 경영비 10%로 피해 30% 되찾음[가정], 지원금 0)."""
    rows = []
    for title, key, crop, sown, year, hit in DISASTERS:
        f, _ = TYPES[key]
        fs = replace(f, sown={crop: sown})
        r = E.after_disaster(fs, year, crop, hit, None, 0.1 * float(E.crop_row(crop)["경영비_천원"]), 0.3)
        opts = [("그대로 두기", r["keep"]), ("되살리기(가정)", r["repair"]), ("갈아엎고 비워 두기", r["abandon"])]
        opts += [(f"다시 심기({c})", v) for c, v in r["replant"].items()]
        for name, v in opts:
            st = stats(v)
            rows.append(dict(사례=title, 재해날=f"{year}-{hit}", 피해율_모형=round(r["model_damage"], 3),
                             이미쓴돈=round(r["sunk"]), 안=name, 보통해=round(st["보통해"]), 하위10=round(st["하위10"]),
                             평균=round(st["평균"])))
        print(title, f"피해율 {r['model_damage']:.0%}, 이미 쓴 돈 {r['sunk']:.0f}")
    df = pd.DataFrame(rows)
    print(df[["사례", "안", "보통해", "하위10"]].to_string(index=False))
    df.to_csv(OUT / "disaster_demo.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from validate import TYPES

    six_types(TYPES, 2026)
    demos(TYPES)
    disaster_demo(TYPES)
