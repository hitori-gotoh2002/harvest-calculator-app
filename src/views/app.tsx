"use client";
import { useCallback, useEffect, useState } from "react";
import { Home, Sprout, Calculator, ShieldCheck, ChevronLeft, MapPin, Bell, RefreshCw, Star, Tractor, ExternalLink } from "lucide-react";
import { post, won, signedWon, pct, mmdd } from "../lib/api";
import type { Calc, DisasterOut, Farm, FarmInput, Flips, Meta, Option } from "../lib/api";
import { DEFAULT_INPUT, DRAIN_LABEL, PRESETS, SUPPORTS, WATER_LABEL, landText } from "../lib/data";

type Screen = "home" | "input" | "result" | "recommend" | "support" | "farm" | "disaster";
const STORE = "harvest-calculator-input-v1";
const TITLE: Record<Screen, string> = {
  home: "", input: "내 땅 알려주기", result: "손익 시뮬레이션", recommend: "작물 추천",
  support: "지원 제도", farm: "내 농장 다시 계산", disaster: "재해 뒤 비교",
};

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
  const [preset, setPreset] = useState(0);
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

  const go = (s: Screen) => { setScreen(s); window.scrollTo({ top: 0 }); };

  const runFarm = useCallback(async (i: FarmInput, o: Option | undefined, year: number) => {
    if (!o) return;
    setFarmBusy(true); setFarmErr("");
    try {
      setFarm(await post<Farm>("farm", { ...i, alt: o.plan.alt, share: o.plan.share, year }));
    } catch (e) { setFarmErr((e as Error).message); setFarm(null); } finally { setFarmBusy(false); }
  }, []);

  const run = useCallback(async (i: FarmInput) => {
    setBusy(true); setError("");
    try {
      const c = await post<Calc>("calc", i);
      setCalc(c); setInput(i); setDraft(i); saveInput(i);
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
    setDraft(i);
    run(i);
  }, [run]);

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
  const summary = calc && <div className="summary-grid">
    <div className="summary-card"><span>지금 작물({calc.input.current_name}) 보통 해</span><strong>{cur ? won(cur.mid) : "심기 어려움"}</strong></div>
    <div className="summary-card"><span>나쁜 해 평균 (가장 나쁜 20%)</span><strong>{cur ? won(cur.bad20) : "-"}</strong></div>
    <div className="summary-card"><span>돈이 가장 모자라는 달</span><strong>{cur ? `${cur.trough_month} ${signedWon(cur.trough)}` : "-"}</strong></div>
    <div className="summary-card warm"><span>수확계산기 추천 (균형)</span><strong>{calc.balanced.label}</strong></div>
  </div>;
  const notice = <p className="notice">지난 34년 날씨와 그해 가격으로 이 땅의 농사를 다시 지어 본 계산 범위예요. 날씨를 예측하지 않아요.
    금액은 2024~2025년 소득 자료 기준이고, 시범 농가 장부로 맞춰 보기 전 단계예요.</p>;
  const errBox = (m: string) => m ? <p className="error" role="alert">{m}</p> : null;

  // ---------------------------------------------------------------- 홈
  const homeView = () => {
    const c0 = farm?.crops[0];
    const rank = c0?.rain_rank;
    const word: [string, string] = rank == null ? ["34년 날씨", "로 계산해요"] : rank < 1 / 3 ? ["비가 적은 편", "이에요"] : rank > 2 / 3 ? ["비가 많은 편", "이에요"] : ["평년과 비슷", "해요"];
    const clim = calc?.climate;
    const progress = c0 ? Math.round(c0.progress * 100) : 0;
    return <>
      <header className="hero">
        <div className="brand"><span><Sprout size={25} /> 수확계산기</span><Bell size={21} /></div>
        <div className="weather"><span>{meta ? `날씨 자료 ${mmdd(meta.weather_until.slice(5))}까지` : "날씨 불러오는 중"}</span><span><MapPin size={16} /> {input.region}</span></div>
        <h1>올해 {eun(input.region)}<br /><b>{word[0]}</b>{word[1]}</h1>
        {c0 && c0.rain != null && <div className="weather-pill">심은 뒤 비 {c0.rain}mm · 평년 {c0.normal_rain}mm · 큰비 {c0.heavy_rain}번</div>}
      </header>
      <main className="home-main">
        {clim && <div className="alert"><Star size={19} fill="currentColor" />{
          clim.wet >= clim.dry && clim.wet > 0 ? `큰비 대비가 먼저예요: 34년 중 ${clim.wet}년에 큰비`
            : clim.dry > 0 ? `가뭄 대비가 먼저예요: 34년 중 ${clim.dry}년 물 부족` : "34년 동안 가뭄·큰비 피해가 드문 땅이에요"}</div>}
        <h2>무엇을 볼까요?</h2>
        <div className="shortcuts">
          <button onClick={() => go("input")}><span><Calculator /></span>손익 계산</button>
          <button onClick={() => go("recommend")}><span><Sprout /></span>작물 추천</button>
          <button onClick={() => go("support")}><span><ShieldCheck /></span>지원 제도</button>
          <button onClick={() => go("farm")}><span><RefreshCw /></span>다시 계산</button>
        </div>
        <button className="disaster" onClick={() => go("disaster")}><strong>재해를 입었나요?</strong>
          <p>그대로 두기·되살리기·다시 심기·비워 두기를 견줘요</p></button>
        {errBox(error)}
        {busy && !calc && <p className="loading">34년 농사를 다시 짓는 중이에요…</p>}
        {summary}
        <div className="section-title"><h2>내 농장</h2><span><MapPin size={15} /> {landText(input)} · {input.area_py.toLocaleString("ko-KR")}평</span></div>
        {farm && calc ? <div className="farm"><h3>{farm.label}</h3><div className="farm-content">
          <div className="ring" style={{ background: `conic-gradient(#55bf6b ${progress}%,#dfe8df ${progress}%)` }}><div>
            <small>{c0?.name} 진행 {progress}%</small><strong>{c0?.days}일째</strong><small>{c0?.length}일 중 · {c0 && mmdd(c0.sown)} 심음</small></div></div>
          <div className="farm-details">
            <p>지금 전망 <b>{won(farm.now.mid)}</b></p>
            <p>심을 때보다 <b>{signedWon(farm.now.mid - farm.first.mid)}</b></p>
            <p>시작 자금 <b>{won(opt(farm.label)?.need90)}</b></p>
            <p>농장 평수 <b>{farm.area_py.toLocaleString("ko-KR")}평</b></p>
          </div></div>
          <small>{mmdd(farm.today)}까지 실제 날씨 반영 · 남은 기간은 지난 34년 날씨</small></div>
          : <div className="farm"><small>{farmErr || "내 농장을 계산하는 중이에요…"}</small></div>}
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
    return <main className="content">
      <h3>예시 농가 불러오기</h3>
      <div className="chips example-chips">{PRESETS.map((p, i) =>
        <button type="button" key={p.name} className={`chip ${preset === i ? "selected" : ""}`} aria-pressed={preset === i}
          onClick={() => { setPreset(i); set(p.set); }}>{p.name}</button>)}</div>
      <label className="field">지역<select value={d.region} onChange={e => set({ region: e.target.value })}>
        {(meta?.regions ?? [{ name: d.region, reservoir_obs: true }]).map(r => <option key={r.name}>{r.name}</option>)}</select>
        <small>{reg && !reg.reservoir_obs ? "이 지역은 저수지 실측 저수율이 아직 없어 계산한 저수율을 써요. 합천·강릉은 실측을 써요." : "날씨 22개 지역, 저수지 실측은 합천·강릉이 연결돼 있어요."}</small></label>
      <Chips label="논이에요, 밭이에요?" items={["논", "밭"] as FarmInput["land"][]} value={d.land} onChange={setLand} />
      <Chips label="물은 어떻게 대요?" items={["수혜구역", "관정", "없음"] as FarmInput["water"][]} value={d.water}
        onChange={v => set({ water: v })} show={v => WATER_LABEL[v]} hint="관정은 전기료가 비용에 들어가요." />
      {d.land === "논" && <Chips label="큰비 뒤 물은 잘 빠지나요?" items={["좋음", "보통", "나쁨"] as FarmInput["drainage"][]}
        value={d.drainage} onChange={v => set({ drainage: v })} show={v => DRAIN_LABEL[v]} />}
      <label className="field">지금(또는 올해 심으려던) 작물<select value={d.current} onChange={e => set({ current: e.target.value })}>
        {crops.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><small>여름 작물(3~7월에 심는 작물)을 골라요.</small></label>
      <Chips label="일손은 어때요?" items={["충분", "보통", "부족"] as FarmInput["labor"][]} value={d.labor} onChange={v => set({ labor: v })}
        hint="부족하면 사람을 사야 해서 손이 많이 가는 작물은 비용이 늘어요." />
      <label className="field">면적 (평)<input type="number" min={100} max={100000} step={100} value={d.area_py}
        onChange={e => set({ area_py: Number(e.target.value) })} /></label>
      <h3>우리 집 돈 사정</h3>
      <div className="row2">
        <label className="field tight">지금 가진 돈 (만 원)<input type="number" min={0} step={50} value={d.money} onChange={e => set({ money: Number(e.target.value) })} /></label>
        <label className="field tight">매달 생활비 (만 원)<input type="number" min={0} step={10} value={d.living} onChange={e => set({ living: Number(e.target.value) })} /></label>
      </div>
      <label className="field tight">다음 해 2월에 남겨야 할 돈 (만 원)<input type="number" min={0} step={50} value={d.need} onChange={e => set({ need: Number(e.target.value) })} />
        <small>5월부터 생활비를 쓰면서 어느 달에도 돈이 바닥나지 않고 이 금액이 남는지 계산해요.</small></label>
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
      <button className="button" disabled={busy} onClick={async () => { if (await run(draft)) go("result"); }}>
        {busy ? "34년 다시 짓는 중…" : "34년 다시 지어 보기"}</button>
    </main>;
  };

  // ---------------------------------------------------------------- 손익 시뮬레이션
  const planCard = (o: Option) => {
    const tags = tagsOf(o);
    return <article className={`plan ${o.label === calc?.balanced.label ? "highlight" : ""}`} key={o.label}>
      <div className="plan-title"><h3>{o.label}</h3><div className="tags">{tags.map(t => <span key={t}>{t}</span>)}</div></div>
      <div className="plan-grid">
        <div><small>한 해 평균</small><strong>{won(o.mean)}</strong></div>
        <div><small>나쁜 해 평균</small><strong>{won(o.bad20)}</strong></div>
        <div><small>필요한 시작 자금</small><strong>{won(o.need90)}</strong></div>
        <div><small>직접 일하는 시간</small><strong>{o.labor_h.toLocaleString("ko-KR")}시간</strong></div>
      </div>
      <p className="survive">가진 돈 {won(input.money)}으로 버티는 경우 <b>{pct(o.survive)}</b>
        <button className="link" onClick={() => { setCalLabel(o.label); setTab("calendar"); window.scrollTo({ top: 0 }); }}>돈 흐름 보기</button></p>
    </article>;
  };
  const resultView = () => {
    if (!calc) return <main className="content">{errBox(error) || <p className="loading">계산하는 중이에요…</p>}</main>;
    const picks = [cur, calc.balanced, calc.best_mean, calc.best_safe, calc.best_easy, ...calc.options].filter(Boolean) as Option[];
    const shown = picks.filter((o, i) => picks.findIndex(x => x.label === o.label) === i).slice(0, 6);
    const o = opt(calLabel) ?? calc.balanced;
    return <main className="content">
      {summary}
      <div className="tabs"><button className={tab === "plans" ? "on" : ""} onClick={() => setTab("plans")}>재배안 비교</button>
        <button className={tab === "calendar" ? "on" : ""} onClick={() => setTab("calendar")}>돈 흐름 달력</button></div>
      {tab === "plans" ? <>
        <p className="muted">지난 34년 날씨 × 가격 5가지 = {calc.cases}가지 경우로 계산했어요. 나쁜 해 = 가장 나쁜 20%의 평균.
          필요한 시작 자금 = 생활비 월 {won(input.living)}을 쓰며 다음 해 2월에 {won(input.need)}이 남도록 처음 가져야 할 돈({calc.cases}가지 중 90% 수준).</p>
        <div className="stack">{shown.map(planCard)}</div>
        <div className="info"><b>균형 추천이란</b><p>한 해 평균과 나쁜 해 평균을 반씩 본 점수가 가장 높은 안이에요. 가진 돈으로 버티는 경우가 낮으면 섞는 비율을 줄인 안도 같이 보세요.</p></div>
        <button className="button secondary" onClick={() => go("recommend")}>원하는 쪽으로 고르기 (작물 추천)</button>
      </> : <>
        <label className="field tight">어떤 안의 달력을 볼까요?<select value={o.label} onChange={e => setCalLabel(e.target.value)}>
          {calc.options.map(x => <option key={x.label}>{x.label}</option>)}</select></label>
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
        </div>
        <p className="muted">비용은 심는 달 40%·키우는 동안 30%·거두는 달 30%, 판 돈은 작물별 정산 시기(예: 벼 10~1월, 논콩 12~3월)에 들어온다고 봤어요.
          실제 정산 날짜에 따라 결과가 크게 바뀌므로 꼭 확인하세요.</p>
      </>}
      {notice}
    </main>;
  };

  // ---------------------------------------------------------------- 작물 추천
  const recommendView = () => {
    if (!calc) return <main className="content">{errBox(error) || <p className="loading">계산하는 중이에요…</p>}</main>;
    const b = calc.balanced, m = calc.best_mean, s = calc.best_safe, e = calc.best_easy, cl = calc.climate;
    const vs = (o: Option) => !cur || o.label === cur.label ? "지금 작물 그대로예요" : `지금보다 보통 해 ${signedWon(o.mid - cur.mid)}`;
    return <main className="content">
      {summary}
      <h2>원하는 쪽을 골라 보세요</h2>
      <div className="stack">
        <article className="recommend green"><b>수익과 안정의 균형 (추천)</b><h3>{b.label}</h3>
          <p>한 해 평균 {won(b.mean)} · 나쁜 해 평균 {won(b.bad20)}</p>
          <p>필요한 시작 자금 {won(b.need90)} · 가진 돈으로 버티는 경우 {pct(b.survive)}</p></article>
        <article className="recommend peach"><b>수익을 더 내고 싶다면?</b><h3>{m.label}</h3>
          <p>보통 해 {won(m.mid)}, 좋은 해 {won(m.hi90)}</p><p>대신 나쁜 쪽 10%는 {won(m.lo10)}까지 내려가요</p><p>{vs(m)}</p></article>
        <article className="recommend blue"><b>나쁜 해를 대비하고 싶다면?</b><h3>{s.label}</h3>
          <p>가장 나쁜 5% 평균이 가장 높은 안: {won(s.worst5)}</p>
          <p>가장 나빴던 한 경우 {won(s.worst)}{cur && cur.label !== s.label ? ` (지금 작물 ${won(cur.worst)})` : ""}</p>
          <p>보통 해 {won(s.mid)} · 직접 일하는 시간 {s.labor_h.toLocaleString("ko-KR")}시간</p></article>
        <article className="recommend green"><b>더 쉽게 짓고 싶다면?</b><h3>{e.label}</h3>
          <p>직접 일하는 시간 {e.labor_h.toLocaleString("ko-KR")}시간{cur ? ` (지금 ${cur.labor_h.toLocaleString("ko-KR")}시간)` : ""}</p>
          <p>보통 해 {won(e.mid)} · {vs(e)}</p></article>
        {cl && <article className="recommend pink"><b>가뭄·큰비가 걱정되나요?</b>
          <h3>34년 중 물 부족 {cl.dry}년, 큰비 {cl.wet}년</h3>
          <p>물 부족 = 물이 모자라 수확이 10% 넘게 준 해, 큰비 = 3일에 100mm 넘는 비가 온 해</p>
          <button className="link" onClick={() => go("support")}>이 땅에 맞는 지원 제도 보기</button></article>}
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
    if (!calc) return <main className="content">{errBox(error) || <p className="loading">계산하는 중이에요…</p>}</main>;
    const years = [2026, ...Array.from({ length: 34 }, (_, i) => 2025 - i)];
    return <main className="content">
      <p className="muted">심은 날부터 기준 날짜까지는 그해 실제 날씨로, 남은 기간은 지난 34년 날씨를 하나씩 이어 붙여 다시 계산해요. 앞으로의 날씨를 맞히지는 않아요.</p>
      <label className="field tight">심은 안<select value={farmPlan} onChange={e => setFarmPlan(e.target.value)}>
        {calc.options.map(o => <option key={o.label}>{o.label}</option>)}</select></label>
      <label className="field tight">어느 해 농사로 볼까요?<select value={farmYear} onChange={e => setFarmYear(Number(e.target.value))}>
        {years.map(y => <option key={y} value={y}>{y === 2026 ? "2026년 (올해)" : y === 2020 ? "2020년 (긴 장마)" : y === 1994 ? "1994년 (큰 가뭄)" : `${y}년`}</option>)}</select>
        <small>지난 해를 고르면 그해 날씨를 처음부터 다시 겪어 봐요.</small></label>
      <button className="button" disabled={farmBusy} onClick={() => runFarm(input, opt(farmPlan), farmYear)}>{farmBusy ? "다시 계산하는 중…" : "다시 계산하기"}</button>
      {errBox(farmErr)}
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
    const crop = dis.crop || input.current;
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
        <label className="field tight">심은 날<input type="date" value={`${dis.year}-${dis.sown}`} onChange={e => e.target.value && set({ sown: e.target.value.slice(5) })} /></label>
      </div>
      <div className="row2">
        <label className="field tight">재해 난 날<input type="date" value={`${dis.year}-${dis.hit}`} onChange={e => e.target.value && set({ hit: e.target.value.slice(5) })} /></label>
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
      {errBox(disErr)}
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

  const back: Screen = screen === "result" || screen === "recommend" ? (screen === "recommend" ? "result" : "home") : "home";
  return <div className="app">
    {screen === "home" ? homeView() : <>
      <header className="page-header"><button aria-label="뒤로 가기" onClick={() => go(back)}><ChevronLeft /></button>
        <h1>{TITLE[screen]}</h1>
        {screen !== "input" && <button className="edit-link" onClick={() => { setDraft(input); go("input"); }}>{landText(input)} · {calc?.input.current_name ?? ""} ▾</button>}
      </header>
      {screen === "input" && inputView()}
      {screen === "result" && resultView()}
      {screen === "recommend" && recommendView()}
      {screen === "support" && supportView()}
      {screen === "farm" && farmView()}
      {screen === "disaster" && disasterView()}
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
