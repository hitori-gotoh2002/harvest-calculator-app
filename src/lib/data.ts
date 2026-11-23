import type { FarmInput } from "./api";

// 대표 사례 (기획안): 합천 저수지 논 3,000평, 물 빠짐 보통, 지금 벼, 가진 돈 1,000만 원, 생활비 월 100만 원
export const DEFAULT_INPUT: FarmInput = {
  region: "합천", land: "논", water: "수혜구역", drainage: "보통", current: "벼", labor: "보통",
  area_py: 3000, prev: "양파·마늘 거둔 뒤", sales: "공판장까지", decision: "",
  money: 1000, living: 100, need: 200, recent: false,
};

// 예시 농가 (분석의 대표 땅 6가지와 같음)
export const PRESETS: { name: string; set: Partial<FarmInput> }[] = [
  { name: "저수지 물 받는 논에서 벼", set: { land: "논", water: "수혜구역", drainage: "보통", current: "벼", prev: "양파·마늘 거둔 뒤", labor: "보통" } },
  { name: "관정 있는 논에서 벼", set: { land: "논", water: "관정", drainage: "보통", current: "벼", prev: "양파·마늘 거둔 뒤", labor: "보통" } },
  { name: "물 댈 곳 없는 논에서 논콩", set: { land: "논", water: "없음", drainage: "보통", current: "콩(논 재배)", prev: "양파·마늘 거둔 뒤", labor: "보통" } },
  { name: "배수 나쁜 논에서 논콩", set: { land: "논", water: "수혜구역", drainage: "나쁨", current: "콩(논 재배)", prev: "양파·마늘 거둔 뒤", labor: "보통" } },
  { name: "관정 있는 밭에서 고추", set: { land: "밭", water: "관정", drainage: "좋음", current: "고추", prev: "없음", labor: "보통" } },
  { name: "물 없는 밭에서 참깨", set: { land: "밭", water: "없음", drainage: "좋음", current: "참깨", prev: "없음", labor: "충분" } },
];

export const WATER_LABEL: Record<FarmInput["water"], string> = { 수혜구역: "마을 저수지", 관정: "지하수(관정)", 없음: "비만 기다림" };
export const DRAIN_LABEL: Record<FarmInput["drainage"], string> = { 좋음: "하루면 빠짐", 보통: "보통", 나쁨: "며칠 고임" };

export function landText(i: FarmInput) {
  const w = i.water === "수혜구역" ? "저수지" : i.water === "관정" ? "관정" : i.land === "논" ? "빗물" : "물 없는";
  return `${i.region} · ${w} ${i.land}${i.land === "논" && i.drainage === "나쁨" ? "(배수 나쁨)" : ""}`;
}

// 지원 제도 (시범판 app/streamlit_app.py 와 같은 내용, 2026년 기준. 지역·연도마다 다르므로 링크에서 확인)
export const SUPPORTS: { name: string; when: string; where: string; what: string; link: string; tags: string[] }[] = [
  { name: "농작물재해보험", when: "작물마다 가입 기간이 정해져 있어요 (예: 벼 4~6월, 콩 6~7월, 양파 10~11월 — 2026년 경주시 안내 기준, 지역·연도마다 다름)",
    where: "지역농협", what: "자연재해로 수확이 줄면 보상. 보험료는 국비 50%(2026년)에 지자체 지원을 더해 시군에 따라 다름",
    link: "https://www.gyeongju.go.kr/open_content/ko/page.do?mnu_uid=3460", tags: ["가뭄", "큰비", "기타"] },
  { name: "농업수입안정보험", when: "품목별 판매 기간 (2026년 20개 품목, 벼·콩·마늘·양파 등)", where: "지역농협(농협손해보험)",
    what: "수확 감소에 더해 값이 떨어져 수입이 줄어도 보상", link: "https://www.heraldk.com/article/2026041818000050714", tags: ["가격"] },
  { name: "가뭄 대비 용수 개발·양수 지원", when: "봄 영농기 전, 가뭄 우려 때 (2026년 3월 농식품부 발표 기준)", where: "시·군청, 한국농어촌공사",
    what: "관정·양수장·저류지 설치, 하천수 양수와 급수 지원 (2026년 가뭄 취약지역 80억 원)",
    link: "https://www.mafra.go.kr/bbs/home/792/577313/artclView.do", tags: ["가뭄"] },
  { name: "재해 복구 지원 (대파대·농약대)", when: "재해 직후 피해 신고", where: "읍·면사무소, 시·군청",
    what: "다시 심는 비용(대파대)과 방제 비용(농약대), 피해가 크면 생계비",
    link: "https://www.mafra.go.kr/bbs/home/792/574885/artclView.do", tags: ["큰비", "가뭄", "기타", "다시심기"] },
  { name: "정책자금 상환 연기·재해대책경영자금", when: "재해 피해 확인 뒤", where: "지역농협, 시·군청",
    what: "피해율에 따라 상환 1~2년 연기·이자 감면, 연 1.8% 경영자금 융자 (2025년 호우 피해 때 기준, 재해마다 다름)",
    link: "https://www.mafra.go.kr/bbs/home/792/574885/artclView.do", tags: ["돈"] },
  { name: "전략작물직불금", when: "봄 신청 (2026년 하계 5월 말 마감)", where: "읍·면사무소, 농업e지",
    what: "논에 콩 등을 심으면 ha당 지원 (논콩 200만 원). 2026년부터 백태는 전년도 이행 농가만",
    link: "https://www.kbmaeil.com/article/20260610500061", tags: ["논콩"] },
  { name: "농업기상재해 조기경보", when: "매일 (문자·앱 알림)", where: "농촌진흥청 (농업e지 앱)",
    what: "필지별 3일 날씨와 최대 9일 재해 예측, 작물별 대응 요령",
    link: "https://m.korea.kr/briefing/actuallyView.do?newsId=148975129", tags: ["가뭄", "큰비", "기타"] },
];
