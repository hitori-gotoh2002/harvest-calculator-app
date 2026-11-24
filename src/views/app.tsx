"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Home, Sprout, Calculator, ShieldCheck, ChevronLeft, MapPin, Bell, RefreshCw, Star, Tractor, ExternalLink,
  LayoutGrid, CloudRain, Shovel, BookOpen } from "lucide-react";
import { post, won, signedWon, pct, mmdd } from "../lib/api";
import type { Calc, ClimateOut, DisasterOut, DrainageOut, Farm, FarmInput, Flips, GridOut, Meta, Option } from "../lib/api";
import { DEFAULT_INPUT, DRAIN_LABEL, PRESETS, SUPPORTS, WATER_LABEL, landText } from "../lib/data";
import { BACKTEST, BACKTEST_NOTE, BACKTEST_SUM, CHECKS, DATA_SOURCES, LIMITS, REGION, STEPS } from "../lib/method";

type Screen = "home" | "input" | "result" | "recommend" | "support" | "farm" | "disaster" | "grid" | "climate" | "drainage" | "method";
const STORE = "harvest-calculator-input-v2";
const TITLE: Record<Screen, string> = {
  home: "", input: "내 땅 알려주기", result: "손익 시뮬레이션", recommend: "작물 추천",
  support: "지원 제도", farm: "내 농장 다시 계산", disaster: "재해 뒤 비교",
  grid: "땅마다 다른 답", climate: "가뭄·큰비 위험", drainage: "배수 공사 값어치", method: "계산 방법·검증",
};
const PUMP_LABEL: Record<FarmInput["pump"], string> = { 일반: "보통 관정 (하루 10mm)", 작은: "작은 관정 (하루 5mm)", 큰: "큰 관정 (하루 15mm)" };
const nameOf = (id: string) => (id === "콩(논 재배)" ? "논콩" : id);

function loadInput(): FarmInput {
  try {
    const s = localStorage.getItem(STORE);
    if (s) return { ...DEFAULT_INPUT, ...JSON.parse(s) };
  } catch { /* 저장소를 못 쓰면 기본값 */ }
  return DEFAULT_INPUT;
}
function saveInput(i: FarmInput) {
  try { localStorage.setItem(STORE, JSON.stringify(i)); } catch { /* 저장 못 해도 계산은 됨 */ }
}
const hasFinal = (w: string) => { const c = w.charCodeAt(w.length - 1); return c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 !== 0; };
const eun = (w: string) => w + (hasFinal(w) ? "은" : "는");

// 숫자 칸: 지우는 중에는 빈 칸을 그대로 두고(0으로 바뀌지 않게), 올바른 숫자일 때만 값을 바꾼다
function NumInput({ value, onChange, min, max, step, placeholder }:
  { value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; placeholder?: string }) {
  const [text, setText] = useState(String(value));
  useEffect(() => { setText(String(value)); }, [value]);
  return <input type="number" inputMode="decimal" value={text} min={min} max={max} step={step} placeholder={placeholder}
    onChange={e => {
      setText(e.target.value);
      const n = Number(e.target.value);
      if (e.target.value !== "" && Number.isFinite(n)) onChange(n);
    }}
    onBlur={() => { if (text === "" || !Number.isFinite(Number(text))) setText(String(value)); }} />;
}

function Chips<T extends string>({ label, items, value, onChange, show, hint }:
  { label: string; items: T[]; value: T; onChange: (v: T) => void; show?: (v: T) => string; hint?: string }) {
  return <fieldset><legend>{label}</legend><div className="chips">{items.map(it =>
    <button type="button" key={it} className={`chip ${value === it ? "selected" : ""}`} aria-pressed={value === it}
      onClick={() => onChange(it)}>{show ? show(it) : it}</button>)}</div>{hint && <small>{hint}</small>}</fieldset>;
}

function PathChart({ farm }: { farm: Farm }) {
  const p = farm.path;
  if (p.length < 2) return null;
  const W = 350, H = 150, L = 8, R = 8, T = 14, B = 22;
  const lo = Math.min(...p.map(x => x.lo10)), hi = Math.max(...p.map(x => x.hi90));
  const X = (i: number) => L + (i * (W - L - R)) / (p.length - 1);
  const Y = (v: number) => T + ((hi - v) * (H - T - B)) / Math.max(1, hi - lo);
  const band = p.map((x, i) => `${X(i)},${Y(x.hi90)}`).concat(p.map((x, i) => `${X(p.length - 1 - i)},${Y(p[p.length - 1 - i].lo10)}`)).join(" ");
  return <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="날짜별 예상 손익 변화">
    <polygon points={band} fill="#dcf1d8" />
    <polyline points={p.map((x, i) => `${X(i)},${Y(x.mid)}`).join(" ")} fill="none" stroke="#1e7a3c" strokeWidth="3" />
    {p.map((x, i) => <circle key={x.date} cx={X(i)} cy={Y(x.mid)} r="3.5" fill="#1e7a3c" />)}
    <text x={L} y={H - 6} fontSize="11" fill="#59665d">{mmdd(p[0].date)}</text>
    <text x={W - R} y={H - 6} fontSize="11" fill="#59665d" textAnchor="end">{mmdd(p[p.length - 1].date)}</text>
  </svg>;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [input, setInput] = useState<FarmInput>(DEFAULT_INPUT);
  const [draft, setDraft] = useState<FarmInput>(DEFAULT_INPUT);
  const [touched, setTouched] = useState(true); // 내 땅을 한 번이라도 넣어 계산했는지 (처음이면 예시 안내)
  const [showAll, setShowAll] = useState(false);
  const [calc, setCalc] = useState<Calc | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [flips, setFlips] = useState<Flips | null>(null);
  const [flipsErr, setFlipsErr] = useState("");
  const [tab, setTab] = useState<"plans" | "calendar">("plans");
  const [calLabel, setCalLabel] = useState("");
  const [farm, setFarm] = useState<Farm | null>(null);
  const [farmBusy, setFarmBusy] = useState(false);
  const [farmErr, setFarmErr] = useState("");
  const [farmPlan, setFarmPlan] = useState("");
  const [farmYear, setFarmYear] = useState(2026);
  const [dis, setDis] = useState({ crop: "", year: 2026, sown: "06-10", hit: "07-20", damage: "", fixCost: "", fixShare: "30", sup1: "0", sup2: "0", example: false });
  const [disOut, setDisOut] = useState<DisasterOut | null>(null);
  const [disBusy, setDisBusy] = useState(false);
  const [disErr, setDisErr] = useState("");
  const [otherCrop, setOtherCrop] = useState("콩(논 재배)");
  // 따로 불러오는 계산 (화면을 열 때, 입력이 바뀌었을 때만)
  const [extra, setExtra] = useState<{ grid?: GridOut; climate?: ClimateOut; drainage?: DrainageOut }>({});
  const [extraKey, setExtraKey] = useState<Record<string, string>>({});
  const [extraBusy, setExtraBusy] = useState("");
  const [extraErr, setExtraErr] = useState<Record<string, string>>({});
  const [extraFail, setExtraFail] = useState<Record<string, string>>({}); // 실패한 요청은 자동으로 다시 보내지 않음
  const [climateAlt, setClimateAlt] = useState("");
  const [drain, setDrain] = useState({ cost: "", support: "0" });
  const [drainApplied, setDrainApplied] = useState<{ cost: number | null; support: number }>({ cost: null, support: 0 });

  const loadExtra = useCallback(async (name: "grid" | "climate" | "drainage", body: object) => {
    const key = JSON.stringify(body);
    setExtraBusy(name); setExtraErr(m => ({ ...m, [name]: "" }));
    try {
      const out = await post<GridOut & ClimateOut & DrainageOut>(name, body);
      setExtra(e => ({ ...e, [name]: out }));
      setExtraKey(k => ({ ...k, [name]: key }));
    } catch (e) {
      setExtraErr(m => ({ ...m, [name]: (e as Error).message }));
      setExtraFail(f => ({ ...f, [name]: key }));
    } finally { setExtraBusy(""); }
  }, []);

  // 화면 이동을 브라우저 기록에 남겨, 폰의 뒤로 가기가 앱 안에서 이전 화면으로 가게 한다
  const go = (s: Screen) => {
    if (s !== screen) window.history.pushState({ screen: s }, "", s === "home" ? window.location.pathname : `#${s}`);
    setScreen(s);
    window.scrollTo({ top: 0 });
  };
  const goBack = () => {
    const st = window.history.state as { screen?: Screen } | null;
    if (st?.screen && st.screen !== "home") window.history.back();
    else go("home");
  };
  useEffect(() => {
    const h = window.location.hash.slice(1) as Screen;
    window.history.replaceState({ screen: "home" }, "", window.location.pathname);
    if (h && h in TITLE && h !== "home") {
      window.history.pushState({ screen: h }, "", `#${h}`);
      setScreen(h);
    }
    const onPop = (e: PopStateEvent) => {
      setScreen(((e.state as { screen?: Screen } | null)?.screen) ?? "home");
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const runFarm = useCallback(async (i: FarmInput, o: Option | undefined, year: number) => {
    if (!o) return;
    setFarmBusy(true); setFarmErr("");
    try {
      setFarm(await post<Farm>("farm", { ...i, alt: o.plan.alt, share: o.plan.share, year }));
    } catch (e) { setFarmErr((e as Error).message); setFarm(null); } finally { setFarmBusy(false); }
  }, []);

  const run = useCallback(async (i: FarmInput, light = false, mine = false) => {
    setBusy(true); setError("");
    try {
      const c = await post<Calc>("calc", i);
      setCalc(c); setInput(i); setDraft(i);
      if (mine) { saveInput(i); setTouched(true); } else { try { if (localStorage.getItem(STORE) !== null) saveInput(i); } catch { /* 저장 못 해도 됨 */ } }
      if (light) return true; // 대금 방식만 바꾼 경우: 보고 있던 달력 그대로
      setCalLabel(c.balanced.label); setFarmPlan(c.balanced.label); setFarmYear(2026);
      setFlips(null); setFlipsErr("");
      // 홈에 바로 보이는 내 농장을 먼저, 오래 걸리는 '답이 뒤집히는 조건'은 그다음에 계산한다
      runFarm(i, c.balanced, 2026).finally(() =>
        post<Flips>("flips", i).then(setFlips).catch(e => setFlipsErr((e as Error).message)));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally { setBusy(false); }
  }, [runFarm]);

  useEffect(() => {
    post<Meta>("meta").then(setMeta).catch(() => { /* 선택지는 기본값으로 */ });
    const i = loadInput();
    try { setTouched(localStorage.getItem(STORE) !== null); } catch { setTouched(false); }
    setDraft(i);
    run(i);
  }, [run]);

  useEffect(() => {
    if (!calc) return;
    const want = (name: "grid" | "climate" | "drainage", body: object) => {
      const key = JSON.stringify(body);
      if (extraKey[name] !== key && extraBusy !== name && extraFail[name] !== key) loadExtra(name, body);
    };
    if (screen === "grid") want("grid", input);
    if (screen === "climate") want("climate", { ...input, alt: climateAlt || undefined });
    if (screen === "drainage" && input.land === "논") want("drainage", { ...input, ...drainApplied });
  }, [screen, calc, input, climateAlt, drainApplied, extraKey, extraBusy, extraFail, loadExtra]);

  const retryExtra = (name: "grid" | "climate" | "drainage") => setExtraFail(f => ({ ...f, [name]: "" }));

  const opt = (label: string) => calc?.options.find(o => o.label === label);
  const cur = calc?.current ?? null;
  const tagsOf = (o: Option) => {
    if (!calc) return [];
    const t: string[] = [];
    if (cur && o.label === cur.label) t.push("지금");
    if (o.label === calc.balanced.label) t.push("균형 추천");
    if (o.label === calc.best_mean.label) t.push("수익 최대");
    if (o.label === calc.best_safe.label) t.push("나쁜 해 대비");
    if (o.label === calc.best_easy.label) t.push("일 적음");
    return t;
  };

  // ---------------------------------------------------------------- 공통 조각
  const openCalendar = (label: string) => { setCalLabel(label); setTab("calendar"); go("result"); };
  const openPlans = () => { setTab("plans"); go("result"); };
  // 요약 카드: 누르면 자세한 화면으로
  const summary = calc && <div className="summary-grid">
    <button className="summary-card" onClick={openPlans}><span>지금 작물({calc.input.current_name}) 보통 해</span><strong>{cur ? won(cur.mid) : "심기 어려움"}</strong></button>
    <button className="summary-card" onClick={openPlans}><span>나쁜 해 평균 (가장 나쁜 20%)</span><strong>{cur ? won(cur.bad20) : "-"}</strong></button>
    <button className="summary-card" onClick={() => cur ? openCalendar(cur.label) : openPlans()}><span>돈이 가장 모자라는 달</span><strong>{cur ? `${cur.trough_month} ${signedWon(cur.trough)}` : "-"}</strong></button>
    <button className="summary-card warm" onClick={() => go("recommend")}><span>수확계산기 추천 (균형)</span><strong>{calc.balanced.label}</strong></button>
  </div>;
  const notice = <p className="notice">지난 34년 날씨와 그해 가격으로 이 땅의 농사를 다시 지어 본 계산 범위예요. 날씨를 예측하지 않아요.
    금액은 2024~2025년 소득 자료 기준이고, 시범 농가 장부로 맞춰 보기 전 단계예요.</p>;
  const errBox = (m: string | undefined, retry?: () => void) => m ? <div className="error" role="alert"><span>{m}</span>
    {retry && <button className="link" onClick={retry}>다시 시도</button>}</div> : null;
  // 기본값과 다르게 적용 중인 조건 (다른 화면에서도 보이게)
  const condList = (i: FarmInput) => {
    const out: string[] = [];
    Object.entries(i.rev_pct).forEach(([c, v]) => { if (v) out.push(`${nameOf(c)} 값 ${v > 0 ? "+" : ""}${v}%`); });
    if (i.land === "논" && i.no_subsidy.length) out.push("콩 직불금 없음");
    if (i.water === "관정" && i.pump !== "일반") out.push(PUMP_LABEL[i.pump]);
    if (i.pay_crop && i.pay_mode !== "default") out.push(`${nameOf(i.pay_crop)} 대금 ${i.pay_mode === "once" ? "한 번에" : "절반 3달 늦게"}`);
    if (i.recent) out.push("최근 20년 날씨만");
    if (i.decision) out.push(`${mmdd(i.decision)}에 작부 결정`);
    return out;
  };
  const conds = calc && condList(input).length > 0 && <div className="conds"><span>적용한 조건: {condList(input).join(" · ")}</span>
    <button className="link" disabled={busy} onClick={() => run({ ...input, rev_pct: {}, no_subsidy: [], pump: "일반", pay_crop: "", pay_mode: "default", recent: false, decision: "" })}>
      모두 기본으로</button></div>;
  const mainError = !calc && errBox(error, () => run(input));

  // ---------------------------------------------------------------- 홈
  const homeView = () => {
    const c0 = farm?.crops[0];
    const rank = c0?.rain_rank;
    const word: [string, string] = rank == null ? ["34년 날씨", "로 계산해요"] : rank < 1 / 3 ? ["비가 적은 편", "이에요"] : rank > 2 / 3 ? ["비가 많은 편", "이에요"] : ["평년과 비슷", "해요"];
    const clim = calc?.climate;
    const progress = c0 ? Math.round(c0.progress * 100) : 0;
    return <>
      <header className="hero">
        <div className="brand"><span><Sprout size={25} /> 수확계산기</span>
          <button className="icon-btn" aria-label="지원 제도와 신청 시기 보기" onClick={() => go("support")}><Bell size={21} /></button></div>
        <div className="weather"><span>{meta ? `날씨 자료 ${mmdd(meta.weather_until.slice(5))}까지` : "날씨 불러오는 중"}</span>
          <button className="icon-btn text" onClick={() => go("input")}><MapPin size={16} /> {input.region}</button></div>
        <h1>올해 {eun(input.region)}<br /><b>{word[0]}</b>{word[1]}</h1>
        {c0 && c0.rain != null && <button className="weather-pill" onClick={() => go("farm")}>심은 뒤 비 {c0.rain}mm · 평년 {c0.normal_rain}mm · 큰비 {c0.heavy_rain}번</button>}
      </header>
      <main className="home-main">
        {!touched && calc && <div className="first"><b>지금은 예시 농가 결과예요</b>
          <p>{landText(input)} {input.area_py.toLocaleString("ko-KR")}평, {calc.input.current_name}. 내 땅 조건을 넣으면 그 땅으로 다시 계산해요.</p>
          <button className="button" onClick={() => go("input")}>내 땅 넣기</button></div>}
        {clim && <button className="alert" onClick={() => go("climate")}><Star size={19} fill="currentColor" />{
          clim.wet >= clim.dry && clim.wet > 0 ? `큰비 대비가 먼저예요: 34년 중 ${clim.wet}년에 큰비`
            : clim.dry > 0 ? `가뭄 대비가 먼저예요: 34년 중 ${clim.dry}년 물 부족` : "34년 동안 가뭄·큰비 피해가 드문 땅이에요"}</button>}
        <h2>무엇을 볼까요?</h2>
        <div className="shortcuts">
          <button onClick={() => go("input")}><span><Calculator /></span>손익 계산</button>
          <button onClick={() => go("recommend")}><span><Sprout /></span>작물 추천</button>
          <button onClick={() => go("support")}><span><ShieldCheck /></span>지원 제도</button>
          <button onClick={() => go("farm")}><span><RefreshCw /></span>다시 계산</button>
          <button onClick={() => go("grid")}><span><LayoutGrid /></span>땅마다 답</button>
          <button onClick={() => go("climate")}><span><CloudRain /></span>가뭄·큰비</button>
          <button onClick={() => go("drainage")}><span><Shovel /></span>배수 공사</button>
          <button onClick={() => go("method")}><span><BookOpen /></span>계산 방법</button>
        </div>
        <button className="disaster" onClick={() => go("disaster")}><strong>재해를 입었나요?</strong>
          <p>그대로 두기·되살리기·다시 심기·비워 두기를 견줘요</p></button>
        {errBox(error, () => run(input))}
        {busy && !calc && <p className="loading">34년 농사를 다시 짓는 중이에요… (처음 열 때는 10초쯤 걸릴 수 있어요)</p>}
        {summary}
        {conds}
        <div className="section-title"><h2>내 농장</h2><span><MapPin size={15} /> {landText(input)} · {input.area_py.toLocaleString("ko-KR")}평</span></div>
        {farm && calc ? <button className="farm" onClick={() => go("farm")}><h3>{farm.label}</h3><div className="farm-content">
          <div className="ring" style={{ background: `conic-gradient(#55bf6b ${progress}%,#dfe8df ${progress}%)` }}><div>
            <small>{c0?.name} 진행 {progress}%</small><strong>{c0?.days}일째</strong><small>{c0?.length}일 중 · {c0 && mmdd(c0.sown)} 심음</small></div></div>
          <div className="farm-details">
            <p>지금 전망 <b>{won(farm.now.mid)}</b></p>
            <p>심을 때보다 <b>{signedWon(farm.now.mid - farm.first.mid)}</b></p>
            <p>시작 자금 <b>{won(opt(farm.label)?.need90)}</b></p>
            <p>농장 평수 <b>{farm.area_py.toLocaleString("ko-KR")}평</b></p>
          </div></div>
          <small>균형 추천을 심었다고 보고 {mmdd(farm.today)}까지 실제 날씨 반영 · 눌러서 자세히</small></button>
          : <div className="farm">{farmErr ? errBox(farmErr, () => calc && runFarm(input, calc.balanced, 2026)) : <small>내 농장을 계산하는 중이에요…</small>}</div>}
        <button className="button" onClick={() => go("input")}>내 땅 조건 바꿔 계산하기</button>
        {notice}
      </main>
    </>;
  };

  // ---------------------------------------------------------------- 입력
  const inputView = () => {
    const d = draft;
    const set = (p: Partial<FarmInput>) => setDraft({ ...d, ...p });
    const crops = meta?.crops[d.land] ?? [{ id: d.current, name: d.current }];
    const setLand = (land: FarmInput["land"]) => {
      const list = meta?.crops[land];
      const current = list && !list.some(c => c.id === d.current) ? list[0].id : d.current;
      set({ land, current, drainage: land === "밭" ? "좋음" : d.drainage === "좋음" ? "보통" : d.drainage });
    };
    const reg = meta?.regions.find(r => r.name === d.region);
    const defDay = d.prev === "양파·마늘 거둔 뒤" ? "06-01" : "04-01";
    const presetIdx = PRESETS.findIndex(p => Object.entries(p.set).every(([k, v]) => d[k as keyof FarmInput] === v));
    const others = crops.filter(c => c.id !== d.current);
    const oc = others.some(c => c.id === otherCrop) ? otherCrop : others[0]?.id ?? "";
    const changed = JSON.stringify(d) !== JSON.stringify(input);
    const submit = async () => {
      // 지금 땅에서 고를 수 없는 작물의 올해 값은 지운다 (보이지 않는 조건이 남지 않게)
      const ids = new Set(crops.map(c => c.id));
      const rev = Object.fromEntries(Object.entries(d.rev_pct).filter(([c, v]) => ids.has(c) && v));
      const clean = { ...d, rev_pct: rev, no_subsidy: d.land === "논" ? d.no_subsidy : [], pay_crop: ids.has(d.pay_crop) ? d.pay_crop : "",
        pay_mode: ids.has(d.pay_crop) ? d.pay_mode : "default" as FarmInput["pay_mode"] };
      if (await run(clean, false, true)) { setTab("plans"); go("result"); }
    };
    return <main className="content">
      {changed && <p className="notice small">바꾼 내용은 아래 <b>34년 다시 지어 보기</b>를 눌러야 결과에 반영돼요.</p>}
      <h3>예시 농가 불러오기</h3>
      <div className="chips example-chips">{PRESETS.map((p, i) =>
        <button type="button" key={p.name} className={`chip ${presetIdx === i ? "selected" : ""}`} aria-pressed={presetIdx === i}
          onClick={() => set(p.set)}>{p.name}</button>)}</div>
      <label className="field">지역<select value={d.region} onChange={e => set({ region: e.target.value })}>
        {(meta?.regions ?? [{ name: d.region, reservoir_obs: true }]).map(r => <option key={r.name}>{r.name}</option>)}</select>
        <small>{reg && !reg.reservoir_obs ? "이 지역은 저수지 실측 저수율이 아직 없어 계산한 저수율을 써요. 합천·강릉은 실측을 써요." : "날씨 22개 지역, 저수지 실측은 합천·강릉이 연결돼 있어요."}</small></label>
      <Chips label="논이에요, 밭이에요?" items={["논", "밭"] as FarmInput["land"][]} value={d.land} onChange={setLand} />
      <Chips label="물은 어떻게 대요?" items={["수혜구역", "관정", "없음"] as FarmInput["water"][]} value={d.water}
        onChange={v => set({ water: v })} show={v => WATER_LABEL[v]} hint="관정은 전기료가 비용에 들어가요." />
      {d.water === "관정" && <Chips label="관정은 하루에 얼마나 대요?" items={["일반", "작은", "큰"] as FarmInput["pump"][]} value={d.pump}
        onChange={v => set({ pump: v })} show={v => PUMP_LABEL[v]} hint="작은 관정은 가뭄 때 물이 모자라기 쉬워요 (기획안: 34년 중 23년)." />}
      {d.land === "논" && <Chips label="큰비 뒤 물은 잘 빠지나요?" items={["좋음", "보통", "나쁨"] as FarmInput["drainage"][]}
        value={d.drainage} onChange={v => set({ drainage: v })} show={v => DRAIN_LABEL[v]} />}
      <label className="field">지금(또는 올해 심으려던) 작물<select value={d.current} onChange={e => set({ current: e.target.value })}>
        {crops.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><small>여름 작물(3~7월에 심는 작물)을 골라요.</small></label>
      <Chips label="일손은 어때요?" items={["충분", "보통", "부족"] as FarmInput["labor"][]} value={d.labor} onChange={v => set({ labor: v })}
        hint="부족하면 사람을 사야 해서 손이 많이 가는 작물은 비용이 늘어요." />
      <label className="field">면적 (평)<NumInput min={100} max={100000} step={100} value={d.area_py} onChange={v => set({ area_py: v })} />
        <small>100~100,000평. 1ha는 약 3,000평이에요.</small></label>
      <h3>우리 집 돈 사정</h3>
      <div className="row2">
        <label className="field tight">지금 가진 돈 (만 원)<NumInput min={0} step={50} value={d.money} onChange={v => set({ money: v })} /></label>
        <label className="field tight">매달 생활비 (만 원)<NumInput min={0} step={10} value={d.living} onChange={v => set({ living: v })} /></label>
      </div>
      <label className="field tight">다음 해 2월에 남겨야 할 돈 (만 원)<NumInput min={0} step={50} value={d.need} onChange={v => set({ need: v })} />
        <small>5월부터 생활비를 쓰면서 어느 달에도 돈이 바닥나지 않고 이 금액이 남는지 계산해요.</small></label>
      <h3>올해 조건 (2026년)</h3>
      <small>계산 기준은 2024~2025년 값이에요. 올해 예상 값이나 직불금 자격이 다르면 넣어 주세요.</small>
      <div className="row2">
        <label className="field tight">{nameOf(d.current)} 판매수입 변화 (%)<NumInput min={-50} max={100} step={1}
          value={d.rev_pct[d.current] ?? 0} onChange={v => set({ rev_pct: { ...d.rev_pct, [d.current]: v } })} /></label>
        {oc && <label className="field tight">다른 작물<select value={oc} onChange={e => setOtherCrop(e.target.value)}>
          {others.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
      </div>
      {oc && <label className="field tight">{nameOf(oc)} 값 변화 (%)<NumInput min={-50} max={100} step={1} value={d.rev_pct[oc] ?? 0}
        onChange={v => set({ rev_pct: { ...d.rev_pct, [oc]: v } })} /></label>}
      {Object.entries(d.rev_pct).some(([, v]) => v) && <div className="chips">{Object.entries(d.rev_pct).filter(([, v]) => v).map(([c, v]) =>
        <button type="button" className="chip selected" key={c} onClick={() => set({ rev_pct: { ...d.rev_pct, [c]: 0 } })}>
          {nameOf(c)} {v > 0 ? "+" : ""}{v}% ✕</button>)}</div>}
      {d.land === "논" && d.current !== "콩(논 재배)" && <label className="check">작년에 콩 직불금을 받지 않았어요<input type="checkbox"
        checked={d.no_subsidy.includes("콩(논 재배)")}
        onChange={e => set({ no_subsidy: e.target.checked ? ["콩(논 재배)"] : [] })} /></label>}
      {d.land === "논" && d.current !== "콩(논 재배)" && <small>2026년부터 백태 전략작물직불금은 전년도 이행 농가만 받아요. 처음 바꾸는 농가라면 체크하세요.</small>}
      <details><summary>더 보기: 앞그루 · 판로 · 작부를 정하는 날</summary>
        <label className="field">앞그루<select value={d.prev} onChange={e => set({ prev: e.target.value as FarmInput["prev"], decision: "" })}>
          <option value="양파·마늘 거둔 뒤">양파·마늘 거둔 뒤 (6월 10일부터)</option><option value="없음">없음 (봄부터 심을 수 있음)</option></select></label>
        <label className="field">팔 수 있는 곳<select value={d.sales} onChange={e => set({ sales: e.target.value })}>
          {(meta?.sales ?? [d.sales]).map(s => <option key={s}>{s}</option>)}</select></label>
        <label className="field">작부를 정하는 날<input type="date" min="2026-01-01" max="2026-10-31" value={`2026-${d.decision || defDay}`}
          onChange={e => set({ decision: e.target.value ? e.target.value.slice(5) : "" })} />
          <small>이 날 뒤에 심는다고 보고 심는 날을 정해요.</small></label>
      </details>
      <details><summary>조건 바꿔 보기</summary>
        <label className="check">최근 20년(2006~2025) 날씨만<input type="checkbox" checked={d.recent} onChange={e => set({ recent: e.target.checked })} /></label>
        <small>켜면 1992~2005년 날씨를 빼고 계산해요. 최근 기후에서 답이 달라지는지 볼 때 써요.</small>
      </details>
      {errBox(error)}
      <div className="cta"><button className="button" disabled={busy} onClick={submit}>
        {busy ? "34년 다시 짓는 중…" : "34년 다시 지어 보기"}</button></div>
    </main>;
  };

  // ---------------------------------------------------------------- 손익 시뮬레이션
  const planCard = (o: Option) => {
    const tags = tagsOf(o);
    const openIt = () => { setCalLabel(o.label); setTab("calendar"); window.scrollTo({ top: 0 }); };
    return <article className={`plan tap ${o.label === calc?.balanced.label ? "highlight" : ""}`} key={o.label} role="button" tabIndex={0}
      aria-label={`${o.label} 돈 흐름 보기`} onClick={openIt} onKeyDown={e => { if (e.key === "Enter") openIt(); }}>
      <div className="plan-title"><h3>{o.label}</h3><div className="tags">{tags.map(t => <span key={t}>{t}</span>)}</div></div>
      <div className="plan-grid">
        <div><small>한 해 평균</small><strong>{won(o.mean)}</strong></div>
        <div><small>나쁜 해 평균</small><strong>{won(o.bad20)}</strong></div>
        <div><small>필요한 시작 자금</small><strong>{won(o.need90)}</strong></div>
        <div><small>직접 일하는 시간</small><strong>{o.labor_h.toLocaleString("ko-KR")}시간</strong></div>
      </div>
      <p className="survive">가진 돈 {won(input.money)}으로 버티는 경우 <b>{pct(o.survive)}</b>
        <span className="link">돈 흐름 보기 ›</span></p>
    </article>;
  };
  const resultView = () => {
    if (!calc) return <main className="content">{mainError || <p className="loading">계산하는 중이에요…</p>}</main>;
    const picks = [cur, calc.balanced, calc.best_mean, calc.best_safe, calc.best_easy, ...calc.options].filter(Boolean) as Option[];
    const uniq = picks.filter((o, i) => picks.findIndex(x => x.label === o.label) === i);
    const shown = showAll ? uniq : uniq.slice(0, 6);
    const o = opt(calLabel) ?? calc.balanced;
    return <main className="content">
      {summary}
      {conds}
      <div className="tabs"><button className={tab === "plans" ? "on" : ""} onClick={() => setTab("plans")}>재배안 비교</button>
        <button className={tab === "calendar" ? "on" : ""} onClick={() => setTab("calendar")}>돈 흐름 달력</button></div>
      {tab === "plans" ? <>
        <p className="muted">지난 34년 날씨 × 가격 5가지 = {calc.cases}가지 경우로 계산했어요. 나쁜 해 = 가장 나쁜 20%의 평균.
          필요한 시작 자금 = 생활비 월 {won(input.living)}을 쓰며 다음 해 2월에 {won(input.need)}이 남도록 처음 가져야 할 돈({calc.cases}가지 중 90% 수준).</p>
        <div className="stack">{shown.map(planCard)}</div>
        {uniq.length > 6 && <button className="button secondary" onClick={() => setShowAll(!showAll)}>
          {showAll ? "주요 안만 보기" : `모든 안 보기 (${uniq.length}가지)`}</button>}
        <div className="info"><b>균형 추천이란</b><p>한 해 평균과 나쁜 해 평균을 반씩 본 점수가 가장 높은 안이에요. 가진 돈으로 버티는 경우가 낮으면 섞는 비율을 줄인 안도 같이 보세요.</p></div>
        <button className="button secondary" onClick={() => go("recommend")}>원하는 쪽으로 고르기 (작물 추천)</button>
      </> : <>
        <label className="field tight">어떤 안의 달력을 볼까요?<select value={o.label} onChange={e => setCalLabel(e.target.value)}>
          {calc.options.map(x => <option key={x.label}>{x.label}</option>)}</select></label>
        {(() => {
          const cs = o.parts.map(p => p.crop);
          const pc = cs.includes(input.pay_crop) ? input.pay_crop : cs[cs.length - 1];
          const mode = input.pay_crop === pc ? input.pay_mode : "default";
          return <div className="row2">
            <label className="field tight">대금 받는 작물<select value={pc} disabled={busy}
              onChange={e => run({ ...input, pay_crop: e.target.value, pay_mode: "default" }, true)}>
              {cs.map(c => <option key={c} value={c}>{nameOf(c)}</option>)}</select></label>
            <label className="field tight">대금 받는 방식<select value={mode} disabled={busy}
              onChange={e => run({ ...input, pay_crop: pc, pay_mode: e.target.value as FarmInput["pay_mode"] }, true)}>
              {(calc.pay_options[pc] ?? []).map(x => <option key={x.mode} value={x.mode}>{x.text}</option>)}</select></label>
          </div>;
        })()}
        {busy && <p className="loading">대금 방식을 바꿔 다시 계산하는 중이에요…</p>}
        <div className="info"><b>{o.trough_month}까지 최대 {won(-o.trough)}을 먼저 써요</b>
          <p>{o.first_pay_month ? `${o.first_pay_month}부터 판 돈이 들어와요. ` : ""}마이너스는 손해가 아니라, 판 돈이 들어오기 전에 비용을 먼저 쓴 만큼이에요.</p></div>
        <div className="months">{o.calendar.map(m => <div key={m.month}
          className={`month ${m.pay ? "pay" : m.mid < 0 ? "spend" : ""}`}><span>{m.month}{m.pay ? " · 입금" : ""}</span>
          <strong>{signedWon(m.mid).replace(" 원", "")}</strong><small>나쁜 쪽 {signedWon(m.lo10).replace(" 원", "")}</small></div>)}</div>
        <p className="muted">이 작물에서 나가고 들어오는 돈만 0부터 더한 값이에요(보통 해, 작은 글씨는 나쁜 쪽 10%). 기계 감가상각비는 빼지 않은 실제 현금 기준이에요.</p>
        <div className="farm stat">
          <p>가진 돈 {won(input.money)} · 생활비 월 {won(input.living)}이면</p>
          <strong className="big">버티는 경우 {pct(o.survive)}</strong>
          <p>다음 해 2월에 {won(input.need)}을 남기려면 처음에 <b>{won(o.need90)}</b>이 있어야 해요 (90% 수준)</p>
          <p>생활비를 빼고 작물에서 남는 돈만으로 2월에 {won(input.need)}을 못 모으는 경우 <b>{pct(o.crop_short)}</b></p>
        </div>
        <p className="muted">비용은 심는 달 40%·키우는 동안 30%·거두는 달 30%, 판 돈은 작물별 정산 시기(예: 벼 10~1월, 논콩 12~3월)에 들어온다고 봤어요.
          실제 정산 날짜에 따라 결과가 크게 바뀌므로 꼭 확인하세요.</p>
      </>}
      {notice}
    </main>;
  };

  // ---------------------------------------------------------------- 작물 추천
  const recommendView = () => {
    if (!calc) return <main className="content">{mainError || <p className="loading">계산하는 중이에요…</p>}</main>;
    const b = calc.balanced, m = calc.best_mean, s = calc.best_safe, e = calc.best_easy, cl = calc.climate;
    const vs = (o: Option) => !cur || o.label === cur.label ? "지금 작물 그대로예요" : `지금보다 보통 해 ${signedWon(o.mid - cur.mid)}`;
    const card = (o: Option) => ({ role: "button", tabIndex: 0, onClick: () => openCalendar(o.label),
      onKeyDown: (ev: React.KeyboardEvent) => { if (ev.key === "Enter") openCalendar(o.label); } });
    return <main className="content">
      {summary}
      {conds}
      <h2>원하는 쪽을 골라 보세요</h2>
      <p className="muted">카드를 누르면 그 안의 돈 흐름 달력을 볼 수 있어요.</p>
      <div className="stack">
        <article className="recommend green tap" {...card(b)}><b>수익과 안정의 균형 (추천)</b><h3>{b.label}</h3>
          <p>한 해 평균 {won(b.mean)} · 나쁜 해 평균 {won(b.bad20)}</p>
          <p>필요한 시작 자금 {won(b.need90)} · 가진 돈으로 버티는 경우 {pct(b.survive)}</p></article>
        <article className="recommend peach tap" {...card(m)}><b>수익을 더 내고 싶다면?</b><h3>{m.label}</h3>
          <p>보통 해 {won(m.mid)}, 좋은 해 {won(m.hi90)}</p><p>대신 나쁜 쪽 10%는 {won(m.lo10)}까지 내려가요</p><p>{vs(m)}</p></article>
        <article className="recommend blue tap" {...card(s)}><b>나쁜 해를 대비하고 싶다면?</b><h3>{s.label}</h3>
          <p>가장 나쁜 5% 평균이 가장 높은 안: {won(s.worst5)}</p>
          <p>가장 나빴던 한 경우 {won(s.worst)}{cur && cur.label !== s.label ? ` (지금 작물 ${won(cur.worst)})` : ""}</p>
          <p>보통 해 {won(s.mid)} · 직접 일하는 시간 {s.labor_h.toLocaleString("ko-KR")}시간</p></article>
        <article className="recommend green tap" {...card(e)}><b>더 쉽게 짓고 싶다면?</b><h3>{e.label}</h3>
          <p>직접 일하는 시간 {e.labor_h.toLocaleString("ko-KR")}시간{cur ? ` (지금 ${cur.labor_h.toLocaleString("ko-KR")}시간)` : ""}</p>
          <p>보통 해 {won(e.mid)} · {vs(e)}</p></article>
        {cl && <article className="recommend pink tap" role="button" tabIndex={0} onClick={() => go("climate")}><b>가뭄·큰비가 걱정되나요?</b>
          <h3>34년 중 물 부족 {cl.dry}년, 큰비 {cl.wet}년</h3>
          <p>물 부족 = 물이 모자라 수확이 10% 넘게 준 해, 큰비 = 3일에 100mm 넘는 비가 온 해</p>
          <p className="link">가뭄·큰비 위험 자세히 보기 ›</p></article>}
      </div>
      <div className="info"><b>답이 뒤집히는 조건</b>
        {flips ? (flips.flips.length ? flips.flips.map(f => <div className="flip" key={f.cond}><span>{f.cond}</span><b>{f.answer}</b></div>)
          : <p>값이나 지원금을 조금 바꿔도 답이 그대로예요.</p>)
          : flipsErr ? <p>{flipsErr}</p> : <p>조건을 하나씩 바꿔 다시 계산하는 중이에요…</p>}
        {calc.breakeven && <p>{calc.input.current_name} 대신 {calc.breakeven.alt}로 모두 바꾸려면 지원금이 {won(calc.breakeven.subsidy_gap)} 더 있어야 해요.</p>}
      </div>
      {(() => {
        const ex = calc.excluded.filter(x => !/맞지 않음|다른 작기/.test(x.why));
        return ex.length > 0 && <p className="muted">이 조건에서 빠진 작물: {ex.map(x => `${x.crop}(${x.why})`).join(", ")}</p>;
      })()}
      <div className="links">
        <button className="button secondary" onClick={() => go("grid")}>땅마다 다른 답</button>
        <button className="button secondary" onClick={() => go("climate")}>가뭄·큰비 위험</button>
        {input.land === "논" && <button className="button secondary" onClick={() => go("drainage")}>배수 공사 값어치</button>}
        <button className="button secondary" onClick={() => go("method")}>계산 방법·검증</button>
      </div>
      <button className="button secondary" onClick={() => go("result")}>재배안 비교로 가기</button>
      {notice}
    </main>;
  };

  // ---------------------------------------------------------------- 지원 제도
  const supportView = () => {
    const mine = new Set<string>(["돈", "가격"]);
    if (calc?.climate?.dry) mine.add("가뭄");
    if (calc?.climate?.wet) mine.add("큰비");
    if (calc && [calc.balanced, cur].some(o => o?.parts.some(p => p.crop === "콩(논 재배)"))) mine.add("논콩");
    const list = [...SUPPORTS].sort((a, b) => Number(b.tags.some(t => mine.has(t))) - Number(a.tags.some(t => mine.has(t))));
    return <main className="content">
      <p className="muted">계산 결과에 맞는 제도를 위에 놓았어요. 2026년 안내 기준이라 지역·연도마다 다를 수 있어요. 신청 전 링크와 담당 기관에서 꼭 확인하세요.</p>
      <div className="stack">{list.map(s => {
        const hit = s.tags.some(t => mine.has(t));
        return <article className={`support ${hit ? "mine" : ""}`} key={s.name}>
          <div className="plan-title"><h3>{s.name}</h3>{hit && <div className="tags"><span>내 땅에 해당</span></div>}</div>
          <p><b>언제</b> {s.when}</p><p><b>어디서</b> {s.where}</p><p>{s.what}</p>
          <a href={s.link} target="_blank" rel="noreferrer">안내 보기 <ExternalLink size={12} /></a></article>;
      })}</div>
    </main>;
  };

  // ---------------------------------------------------------------- 내 농장 다시 계산
  const farmView = () => {
    if (!calc) return <main className="content">{mainError || <p className="loading">계산하는 중이에요…</p>}</main>;
    const years = [2026, ...Array.from({ length: 34 }, (_, i) => 2025 - i)];
    return <main className="content">
      <p className="muted">심은 날부터 기준 날짜까지는 그해 실제 날씨로, 남은 기간은 지난 34년 날씨를 하나씩 이어 붙여 다시 계산해요. 앞으로의 날씨를 맞히지는 않아요.</p>
      <label className="field tight">심은 안<select value={farmPlan} disabled={farmBusy}
        onChange={e => { setFarmPlan(e.target.value); runFarm(input, opt(e.target.value), farmYear); }}>
        {calc.options.map(o => <option key={o.label}>{o.label}</option>)}</select></label>
      <label className="field tight">어느 해 농사로 볼까요?<select value={farmYear} disabled={farmBusy}
        onChange={e => { const y = Number(e.target.value); setFarmYear(y); runFarm(input, opt(farmPlan), y); }}>
        {years.map(y => <option key={y} value={y}>{y === 2026 ? "2026년 (올해)" : y === 2020 ? "2020년 (긴 장마)" : y === 1994 ? "1994년 (큰 가뭄)" : `${y}년`}</option>)}</select>
        <small>지난 해를 고르면 그해 날씨를 처음부터 다시 겪어 봐요.</small></label>
      {farmBusy && <p className="loading">다시 계산하는 중이에요…</p>}
      {errBox(farmErr, () => runFarm(input, opt(farmPlan), farmYear))}
      {farm && <>
        <div className="farm stat"><p>{farm.year}년 · {farm.label} · {mmdd(farm.today)} 기준</p>
          <strong className="big">{won(farm.now.mid)}</strong>
          <p>심을 때 전망 {won(farm.first.mid)}보다 {signedWon(farm.now.mid - farm.first.mid)}</p>
          <p>나쁜 쪽 10% {won(farm.now.lo10)} ~ 좋은 쪽 10% {won(farm.now.hi90)}</p>
          {farm.actual != null && <p>그해 실제 날씨·값으로 끝까지 지었다면 <b>{won(farm.actual)}</b></p>}
        </div>
        <PathChart farm={farm} />
        <p className="muted">진한 선 = 보통 해 전망, 연한 띠 = 나쁜 쪽 10%~좋은 쪽 10%. 15일마다 다시 계산했어요.</p>
        <div className="stack">{farm.crops.map(c => <article className="plan" key={c.crop}>
          <div className="plan-title"><h3>{c.name}</h3><div className="tags"><span>{mmdd(c.sown)} 심음</span></div></div>
          <div className="plan-grid">
            <div><small>지난 날</small><strong>{c.days}일 / {c.length}일</strong></div>
            <div><small>심은 뒤 비</small><strong>{c.rain != null ? `${c.rain}mm (평년 ${c.normal_rain}mm)` : "-"}</strong></div>
            <div><small>큰비</small><strong>{c.heavy_rain ?? 0}번</strong></div>
            <div><small>물 충족</small><strong>{c.water_ok != null ? pct(c.water_ok) : "-"}</strong></div>
          </div></article>)}</div>
      </>}
    </main>;
  };

  // ---------------------------------------------------------------- 재해 뒤 비교
  const disasterView = () => {
    const crops = meta?.crops[input.land] ?? [{ id: input.current, name: input.current }];
    const crop = crops.some(c => c.id === dis.crop) ? dis.crop : input.current;
    const set = (p: Partial<typeof dis>) => setDis({ ...dis, ...p });
    const submit = async () => {
      setDisBusy(true); setDisErr("");
      const base = dis.example ? { ...input, land: "논", water: "수혜구역", drainage: "나쁨", current: "콩(논 재배)" } : input;
      try {
        setDisOut(await post<DisasterOut>("disaster", {
          ...base, crop: dis.example ? "콩(논 재배)" : crop, year: dis.year, sown: dis.sown, hit: dis.hit,
          damage: dis.damage === "" ? null : Number(dis.damage) / 100,
          fix_cost: dis.fixCost === "" ? null : Number(dis.fixCost), fix_share: Number(dis.fixShare) / 100,
          fix_support: Number(dis.sup1), replant_support: Number(dis.sup2),
        }));
      } catch (e) { setDisErr((e as Error).message); setDisOut(null); } finally { setDisBusy(false); }
    };
    return <main className="content">
      <p className="muted">재해가 난 날 기준으로 남은 기간을 지난 34년 날씨로 계산해, 이미 쓴 비용까지 넣은 그해 손익으로 견줘요.</p>
      <div className="chips"><button type="button" className={`chip ${dis.example ? "selected" : ""}`}
        onClick={() => set(dis.example ? { example: false, year: 2026, sown: "06-10", hit: "07-20" } : { example: true, year: 2020, sown: "06-15", hit: "07-14" })}>
        예시: 2020년 장마, 배수 나쁜 논 논콩</button></div>
      {!dis.example && <label className="field tight">피해 입은 작물<select value={crop} onChange={e => set({ crop: e.target.value })}>
        {crops.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
      <div className="row2">
        <label className="field tight">연도<select value={dis.year} onChange={e => set({ year: Number(e.target.value) })}>
          {[2026, ...Array.from({ length: 34 }, (_, i) => 2025 - i)].map(y => <option key={y} value={y}>{y}년</option>)}</select></label>
        <label className="field tight">심은 날<input type="date" min={`${dis.year}-01-01`} max={`${dis.year}-12-31`} value={`${dis.year}-${dis.sown}`} onChange={e => e.target.value && set({ sown: e.target.value.slice(5) })} /></label>
      </div>
      <div className="row2">
        <label className="field tight">재해 난 날<input type="date" min={`${dis.year}-01-01`} max={`${dis.year}-12-31`} value={`${dis.year}-${dis.hit}`} onChange={e => e.target.value && set({ hit: e.target.value.slice(5) })} /></label>
        <label className="field tight">현장 피해율 (%)<input type="number" min={0} max={100} placeholder="비우면 계산값" value={dis.damage} onChange={e => set({ damage: e.target.value })} /></label>
      </div>
      <details><summary>되살리기 비용·지원금 (가정 바꾸기)</summary>
        <div className="row2">
          <label className="field tight">되살리는 데 드는 돈 (만 원)<input type="number" min={0} placeholder="비우면 경영비의 10%" value={dis.fixCost} onChange={e => set({ fixCost: e.target.value })} /></label>
          <label className="field tight">되살릴 수 있는 피해 몫 (%)<input type="number" min={0} max={100} value={dis.fixShare} onChange={e => set({ fixShare: e.target.value })} /></label>
          <label className="field tight">농약대 등 지원 (만 원)<input type="number" min={0} value={dis.sup1} onChange={e => set({ sup1: e.target.value })} /></label>
          <label className="field tight">대파대 등 지원 (만 원)<input type="number" min={0} value={dis.sup2} onChange={e => set({ sup2: e.target.value })} /></label>
        </div></details>
      <button className="button" disabled={disBusy} onClick={submit}>{disBusy ? "견주는 중…" : "세 가지 안 견주기"}</button>
      {errBox(disErr, submit)}
      {disOut && <>
        <div className="info"><b>{disOut.year}년 {mmdd(disOut.hit)} · {disOut.crop} ({mmdd(disOut.sown)} 심음)</b>
          <p>재해 날까지 큰비 {disOut.heavy_rain}번 · 계산한 피해율 {pct(disOut.model_damage)}{Math.abs(disOut.damage - disOut.model_damage) > 1e-6 ? ` (넣은 피해율 ${pct(disOut.damage)}로 계산)` : ""}</p>
          <p>이미 쓴 돈 {won(disOut.sunk)} · 되살리기에 {won(disOut.fix_cost)}을 들이면 피해의 {pct(disOut.fix_share)}를 되찾는다고 봤어요(가정)</p></div>
        <div className="stack">{[...disOut.options].sort((a, b) => b.mid - a.mid).map(o =>
          <article className={`plan ${o.name === disOut.best ? "highlight" : ""}`} key={o.name}>
            <div className="plan-title"><h3>{o.name}</h3>{o.name === disOut.best && <div className="tags"><span>가장 나음</span></div>}</div>
            <div className="plan-grid"><div><small>그해 손익 (보통 해)</small><strong>{won(o.mid)}</strong></div>
              <div><small>나쁜 쪽 10%</small><strong>{won(o.lo10)}</strong></div></div>
            {o.sow && <p className="survive">{mmdd(o.sow)}에 다시 심어요</p>}</article>)}</div>
        {disOut.next_year.length > 0 && <p className="muted">해를 넘겨 거두는 {disOut.next_year.join("·")}는 그대로 두기 뒤에도 심을 수 있어 같은 해 비교에서 뺐어요.</p>}
        <p className="muted">되살리기 비용·효과와 지원 단가는 가정이에요. 현장 값과 지원 결정이 나오면 바꿔 넣으세요.</p>
      </>}
    </main>;
  };

  // ---------------------------------------------------------------- 땅마다 다른 답 (논 9가지)
  const loading = (name: string) => extraBusy === name ? <p className="loading">34년 농사를 다시 짓는 중이에요…</p> : null;
  const gridView = () => {
    const g = extra.grid;
    const waters: [string, string][] = [["수혜구역", "저수지 논"], ["관정", "관정 논"], ["없음", "빗물 논"]];
    const drs = ["좋음", "보통", "나쁨"];
    const cell = (w: string, dd: string) => g?.cells.find(x => x.water === w && x.drainage === dd);
    return <main className="content">
      <p className="muted">같은 {input.region}의 논이라도 물 대는 방법과 물 빠짐에 따라 답이 갈려요. 지금 벼를 심는 논, 일손 {input.labor} 기준이에요.
        평균 소득 자료(직불금 포함)의 1위 작물과 수확계산기의 답을 나란히 봐요.</p>
      {!calc && (mainError || <p className="loading">계산하는 중이에요…</p>)}
      {errBox(extraErr.grid, () => retryExtra("grid"))}{loading("grid")}
      {g && <>
        <div className="grid9"><div />{drs.map(dd => <div key={dd} className="gh">물 빠짐 {dd}</div>)}
          {waters.map(([w, wl]) => <Fragment key={w}><div className="gr">{wl}</div>{drs.map(dd => {
            const c = cell(w, dd);
            return c ? <div key={dd} className={`gc ${c.same ? "" : "diff"}`}><b>{c.answer}</b><small>소득 자료 1위 {c.stat_best}</small></div> : <div key={dd} />;
          })}</Fragment>)}
        </div>
        <p className="muted">주황 칸 = 소득 자료 1위와 다른 답 ({g.cells.filter(c => !c.same).length}곳). 빗물 논은 물이 없어 벼를 못 심는 경우라 다른 작물만 견줘요.</p>
        <table className="tbl"><thead><tr><th>땅</th><th>벼 평균 / 나쁜 해</th><th>논콩 평균 / 나쁜 해</th></tr></thead><tbody>
          {g.cells.map(c => <tr key={c.water + c.drainage}><td>{waters.find(x => x[0] === c.water)?.[1]} · {c.drainage}</td>
            <td>{c.rice_mean != null ? `${c.rice_mean} / ${c.rice_bad20}` : "못 심음"}</td>
            <td>{c.soy_mean != null ? `${c.soy_mean} / ${c.soy_bad20}` : "-"}</td></tr>)}</tbody></table>
        <p className="muted">만 원, {g.area_py.toLocaleString("ko-KR")}평 기준. 나쁜 해 = 가장 나쁜 20%의 평균.</p>
        <div className="info"><b>누가 쓰나요</b><p>농업기술센터는 전환을 권할 논과 말릴 논을, 지자체는 지원금·배수 사업을 쓸 곳을 고를 수 있어요.</p></div>
      </>}
    </main>;
  };

  // ---------------------------------------------------------------- 가뭄·큰비 위험
  const climateView = () => {
    const c = extra.climate;
    const h = c?.hedge;
    const range = (xs: number[]) => { const a = Math.min(...xs), b = Math.max(...xs); return a === b ? `${a}` : `${a}~${b}`; };
    return <main className="content">
      {!calc && (mainError || <p className="loading">계산하는 중이에요…</p>)}
      {errBox(extraErr.climate, () => retryExtra("climate"))}{loading("climate")}
      {c && <>
        {h && <>
          <h3>가장 가물었던 {h.n}년과 비가 가장 많았던 {h.n}년</h3>
          <label className="field tight">함께 견줄 작물<select value={climateAlt || h.alt} onChange={e => setClimateAlt(e.target.value)}>
            {h.alts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          <table className="tbl"><thead><tr><th>{c.area_py.toLocaleString("ko-KR")}평</th><th>가문 해</th><th>비 많은 해</th><th>{h.years}년 평균</th><th>흔들림</th><th>나쁜 해</th></tr></thead>
            <tbody>{h.rows.map(r => <tr key={r.name}><td>{r.name}</td><td>{r.dry}</td><td>{r.wet}</td><td>{r.mean}</td><td>{r.std}</td><td>{r.bad20}</td></tr>)}</tbody></table>
          <p className="muted">만 원. 해마다 손익(가격 5가지 평균) {h.years}개 기준. 흔들림 = 해마다 손익의 표준편차, 나쁜 해 = 가장 나쁜 20%의 평균.
            가문 해 {h.dry_years.join("·")}, 비 많은 해 {h.wet_years.join("·")} ({c.current_name} 작기의 비 − 증발량 기준).</p>
          <div className="info"><b>반반 섞으면</b><p>{h.years}년 평균은 비슷하면서 해마다 흔들리는 폭이 {range(h.std_cut.filter((x): x is number => x != null).map(x => Math.round(x * 100)))}% 줄고,
            나쁜 해 평균이 {range(h.bad_gain)}만 원 높아져요. 몇 %를 섞을지는 땅의 물 사정과 가진 돈에 따라 달라 작물 추천에서 계산해요.</p></div>
        </>}
        <h3>큰비가 잦아지나요?</h3>
        <div className="farm stat"><p>6~9월에 3일 100mm 넘는 비가 온 해 ({c.region})</p>
          <strong className="big">{pct(c.trend.all)} → {pct(c.trend.recent)}</strong>
          <p>{c.trend.all_years}년 전체 → 최근 {c.trend.recent_years}년</p>
          {c.trend.cur_all != null && <p>{c.current_name} 그대로 평균 {won(c.trend.cur_all)} → 최근 15년 날씨만 {won(c.trend.cur_recent)}</p>}</div>
        <h3>가뭄 위험은 어떤 땅에 몰리나요?</h3>
        <p className="muted">{c.region}, 34년 중 물이 모자라 수확이 10% 넘게 준 해 (계산)</p>
        <div className="bars">{c.drought.map(x => <div className="barrow" key={x.land}><span>{x.land}</span>
          <div className="bartrack"><div className="barfill" style={{ width: `${(x.dry / Math.max(1, x.years)) * 100}%` }} /></div><b>{x.dry}년</b></div>)}</div>
        <p className="muted">저수지가 바닥나는 깊은 가뭄(2022년)은 계산이 얕게 봐요. 물 댈 곳이 없는 땅부터 작물 바꾸기와 용수 지원을 먼저 보세요.</p>
        {c.water && <><h3>물과 전기도 아껴요</h3>
          <div className="farm stat"><p>관정으로 물을 대는 같은 논에서 {c.current_name} {c.water.cur_mm}mm → {c.water.alt_name} {c.water.alt_mm}mm</p>
            <strong className="big">한 해 지하수 약 {c.water.tons.toLocaleString("ko-KR")}톤</strong>
            <p>양수 전기 약 {c.water.kwh.toLocaleString("ko-KR")}kWh 절약 ({c.area_py.toLocaleString("ko-KR")}평, 1톤에 {c.water.kwh_per_m3}kWh 가정)</p></div></>}
        <button className="button secondary" onClick={() => go("support")}>가뭄·큰비 지원 제도 보기</button>
      </>}
    </main>;
  };

  // ---------------------------------------------------------------- 배수 공사 값어치
  const drainageView = () => {
    if (input.land !== "논") return <main className="content"><p className="muted">배수 공사 계산은 논에서만 해요. 내 땅 알려주기에서 논을 골라 주세요.</p>
      <button className="button" onClick={() => go("input")}>내 땅 알려주기</button></main>;
    const x = extra.drainage;
    return <main className="content">
      <p className="muted">같은 논을 물 빠짐 '나쁨·보통·좋음'으로 바꿔 34년 × 가격 5가지를 다시 계산해, 물 빠짐을 고치면 한 해에 얼마나 나아지는지 봐요.
        지금 물 빠짐: <b>{DRAIN_LABEL[input.drainage]}</b></p>
      <div className="row2">
        <label className="field tight">공사비 (만 원)<input type="number" min={0} step={50} placeholder={`${Math.round(650 * input.area_py / 3000)} (무굴착 암거)`}
          value={drain.cost} onChange={e => setDrain({ ...drain, cost: e.target.value })} /></label>
        <label className="field tight">지원받는 몫 (%)<input type="number" min={0} max={100} step={10} value={drain.support}
          onChange={e => setDrain({ ...drain, support: e.target.value })} /></label>
      </div>
      <button className="button" disabled={extraBusy === "drainage"} onClick={() => setDrainApplied({ cost: drain.cost === "" ? null : Number(drain.cost), support: Number(drain.support) })}>
        {extraBusy === "drainage" ? "계산하는 중…" : "다시 계산"}</button>
      {!calc && (mainError || <p className="loading">계산하는 중이에요…</p>)}
      {errBox(extraErr.drainage, () => retryExtra("drainage"))}{loading("drainage")}
      {x && <>
        <div className="stack">{x.levels.map(l => <article className={`plan ${l.level === x.now ? "highlight" : ""}`} key={l.level}>
          <div className="plan-title"><h3>물 빠짐 {l.level}</h3>{l.level === x.now && <div className="tags"><span>지금</span></div>}</div>
          <div className="plan-grid">
            <div><small>{x.current_name} 그대로 평균</small><strong>{won(l.cur_mean)}</strong></div>
            <div><small>나쁜 해 평균</small><strong>{won(l.cur_bad20)}</strong></div>
            <div><small>한 해 늘어나는 돈</small><strong>{l.level === x.now || l.cur_gain == null ? "-" : signedWon(l.cur_gain)}</strong></div>
            <div><small>공사비 되찾는 기간</small><strong>{l.level === x.now ? "-" : l.cur_payback != null ? `약 ${l.cur_payback}년` : "되찾지 못함"}</strong></div>
          </div>
          <p className="survive">균형 추천: {l.bal_label} · 평균 {won(l.bal_mean)}</p></article>)}</div>
        <p className="muted">공사비 {won(x.cost)} 중 자부담 {won(x.own)}으로 계산했어요. 예시: 무굴착 암거배수 ha당 650만 원(국립식량과학원 시험 값), 지원금은 시군·사업마다 달라요.
          한 해 5만 원(3,000평 기준)도 안 늘면 '되찾지 못함'으로 봐요.</p>
      </>}
    </main>;
  };

  // ---------------------------------------------------------------- 계산 방법·검증 (기획안 원문)
  const methodView = () => <main className="content">
    <p className="muted">기획안 '데이터 활용 전략'의 자료, 분석 방법, 검증 결과예요. 검증(분석 결과 5)과 지역 통계는 여러 해를 다시 돌린 분석 결과라 저장된 값을 보여 줘요.
      나머지 화면의 숫자는 모두 이 앱이 그 자리에서 계산해요.</p>
    <h3>어떤 데이터를 쓰나</h3>
    <div className="stack">{DATA_SOURCES.map(s => <article className="support" key={s.name}><div className="plan-title"><h3>{s.name}</h3></div>
      <p>{s.source}</p><p><b>쓴 항목</b> {s.used}</p><p><b>쓰는 곳</b> {s.where}</p></article>)}</div>
    <h3>{REGION.title}</h3>
    <table className="tbl"><tbody>{REGION.facts.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
    <p className="muted">{REGION.why}</p>
    <h3>계산 순서와 공식</h3>
    <div className="stack">{STEPS.map(s => <article className="support" key={s.title}><div className="plan-title"><h3>{s.title}</h3></div><p>{s.body}</p></article>)}</div>
    <h3>분석 결과 5: 과거로 돌아가 채점했어요</h3>
    <p className="muted">2015~2025년 각 해에 그전 자료만으로 답을 정하고, 그해 실제 날씨·가격으로 채점했어요.</p>
    <table className="tbl"><thead><tr><th>땅 (지금 작물)</th><th>수확계산기의 답</th><th>지금 작물보다</th><th>소득 자료 1위보다</th></tr></thead>
      <tbody>{BACKTEST.map(b => <tr key={b.land}><td>{b.land}</td><td>{b.answer}</td><td>{b.vsNow}</td><td>{b.vsStat}</td></tr>)}</tbody></table>
    <p className="muted">{BACKTEST_NOTE}</p>
    <div className="info"><b>정리하면</b><p>{BACKTEST_SUM}</p></div>
    <h3>실제 기록과 견줬어요</h3>
    <div className="stack">{CHECKS.map(c => <article className="support" key={c.name}><div className="plan-title"><h3>{c.name}</h3></div>
      <p><b>무엇과</b> {c.against}</p><p><b>결과</b> {c.result}</p></article>)}</div>
    <h3>남은 한계</h3>
    <ul className="limits">{LIMITS.map(l => <li key={l}>{l}</li>)}</ul>
  </main>;

  return <div className="app">
    {screen === "home" ? homeView() : <>
      <header className="page-header"><button aria-label="뒤로 가기" onClick={goBack}><ChevronLeft /></button>
        <h1>{TITLE[screen]}</h1>
        {screen !== "input" && <button className="edit-link" onClick={() => { setDraft(input); go("input"); }}>{landText(input)} · {calc?.input.current_name ?? ""} ▾</button>}
      </header>
      {screen === "input" && inputView()}
      {screen === "result" && resultView()}
      {screen === "recommend" && recommendView()}
      {screen === "support" && supportView()}
      {screen === "farm" && farmView()}
      {screen === "disaster" && disasterView()}
      {screen === "grid" && gridView()}
      {screen === "climate" && climateView()}
      {screen === "drainage" && drainageView()}
      {screen === "method" && methodView()}
    </>}
    {screen !== "input" && <nav className="bottom-nav" aria-label="주 메뉴">
      <button className={screen === "home" ? "active" : ""} onClick={() => go("home")}><Home /><span>홈</span></button>
      <button className={screen === "recommend" ? "active" : ""} onClick={() => go("recommend")}><Sprout /><span>작물 추천</span></button>
      <button className={screen === "result" ? "active" : ""} onClick={() => go("result")}><Calculator /><span>시뮬레이션</span></button>
      <button className={screen === "support" ? "active" : ""} onClick={() => go("support")}><ShieldCheck /><span>지원제도</span></button>
      <button className={screen === "farm" || screen === "disaster" ? "active" : ""} onClick={() => go("farm")}><Tractor /><span>내 농장</span></button>
    </nav>}
  </div>;
}
