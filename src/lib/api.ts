// 계산 API (engine/service.py) 호출과 응답 모양. 금액은 모두 입력 면적 기준 만 원.

export type FarmInput = {
  region: string;
  land: "논" | "밭";
  water: "수혜구역" | "관정" | "없음";
  drainage: "좋음" | "보통" | "나쁨";
  current: string;
  labor: "충분" | "보통" | "부족";
  area_py: number;
  prev: "없음" | "양파·마늘 거둔 뒤";
  sales: string;
  decision: string; // "MM-DD", 비우면 앞그루에 따라 6월 1일 또는 4월 1일
  money: number; // 지금 가진 돈
  living: number; // 매달 생활비
  need: number; // 다음 해 2월에 남겨야 할 돈
  recent: boolean; // 최근 20년 날씨만
};

export type Meta = {
  regions: { name: string; reservoir_obs: boolean }[];
  crops: Record<"논" | "밭", { id: string; name: string }[]>;
  sales: string[];
  prev: string[];
  weather_until: string;
  year: number;
};

export type MonthCell = { month: string; mid: number; lo10: number; pay: boolean };

export type Option = {
  plan: { alt: string; share: number };
  label: string;
  parts: { crop: string; name: string; share: number }[];
  mean: number; mid: number; lo10: number; hi90: number;
  bad20: number; worst5: number; worst: number; loss_share: number; score: number;
  labor_h: number; need90: number; survive: number; crop_short: number;
  trough: number; trough_month: string; first_pay_month: string | null;
  calendar: MonthCell[];
};

export type Calc = {
  input: FarmInput & { current_name: string };
  state: { reservoir_rate: number | null; reservoir_source: string; state: string | null };
  reservoir_obs: boolean;
  current: Option | null;
  balanced: Option;
  best_mean: Option;
  best_safe: Option;
  best_easy: Option;
  options: Option[];
  climate: { years: number; dry: number; wet: number } | null;
  breakeven: { alt: string; subsidy_gap: number; price_change: number | null } | null;
  excluded: { crop: string; why: string }[];
  cases: number;
  years: number[];
};

export type Flips = { base: string; flips: { cond: string; answer: string; changed: boolean }[] };

export type FarmPoint = { date: string; mid: number; lo10: number; hi90: number; bad20: number };
export type Farm = {
  label: string; year: number; today: string; weather_until: string;
  path: FarmPoint[]; first: FarmPoint; now: FarmPoint; actual: number | null; area_py: number;
  crops: {
    crop: string; name: string; sown: string; days: number; length: number; progress: number;
    rain?: number; normal_rain?: number; rain_rank?: number; heavy_rain?: number; water_ok?: number;
  }[];
};

export type DisasterOut = {
  crop: string; year: number; sown: string; hit: string; model_damage: number; damage: number;
  sunk: number; fix_cost: number; fix_share: number; heavy_rain: number; best: string; next_year: string[];
  area_py: number;
  options: { name: string; mid: number; lo10: number; mean: number; sow?: string }[];
};

export async function post<T>(name: string, body: object = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("계산 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요");
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* 본문이 JSON이 아님 */
  }
  if (!res.ok) {
    const msg = data && typeof data === "object" && "error" in data ? String((data as { error: unknown }).error) : "";
    throw new Error(msg || `계산 서버 오류 (${res.status})`);
  }
  return data as T;
}

export const won = (v: number | null | undefined) =>
  v == null ? "-" : `${Math.round(v).toLocaleString("ko-KR")}만 원`;
export const signedWon = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v)).toLocaleString("ko-KR")}만 원`;
export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const mmdd = (s: string) => `${Number(s.slice(0, 2))}월 ${Number(s.slice(3, 5))}일`;
