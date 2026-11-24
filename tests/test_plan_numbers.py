"""기획안 보완본(2026-11-25 제출) '데이터 활용 전략'의 숫자를 앱 계산 API가 그대로 내는지 지키는 테스트.

기대값은 모두 기획안 본문·표에 적힌 값이다(코드로 다시 계산한 값이 아님). 엔진·자료·계산 서비스를 고친 뒤
이 테스트가 깨지면 기획안 숫자가 바뀐 것이므로, 기획안을 고치거나 변경을 되돌려야 한다.

실행: python -m unittest discover -s tests -v   (저장소 맨 위에서, numpy·pandas 필요, 1분쯤)
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import http_util  # noqa: E402
import service  # noqa: E402

R = service.ROUTES
SOY = "콩(논 재배)"
BAD_SOY = dict(drainage="나쁨", current=SOY)  # 물 빠짐 나쁜 저수지 논, 지금 논콩


def by_label(out):
    return {o["label"]: o for o in out["options"]}


class 대표사례(unittest.TestCase):
    """기획안 서비스 세부 내용 '대표 사례' 표: 합천 저수지 논 3,000평, 물 빠짐 보통, 가진 돈 1,000만 원, 생활비 월 100만 원."""

    @classmethod
    def setUpClass(cls):
        cls.out = R["calc"]({})
        cls.o = by_label(cls.out)

    def test_네_가지_안의_평균_나쁜해_시작자금_버팀(self):
        expect = {  # 한 해 평균, 나쁜 해 평균, 필요한 시작 자금, 1,000만 원으로 버티는 경우(%)
            "벼 그대로": (541, 351, 924, 100),
            "벼 70% + 논콩 30%": (541, 385, 929, 100),
            "벼 50% + 논콩 50%": (541, 401, 1011, 82),
            "논콩으로 모두 바꾸기": (542, 363, 1317, 0),
        }
        for label, (mean, bad, need, surv) in expect.items():
            with self.subTest(label):
                x = self.o[label]
                self.assertEqual((x["mean"], x["bad20"], x["need90"], round(x["survive"] * 100)), (mean, bad, need, surv))

    def test_균형_추천은_논콩_50퍼센트(self):
        self.assertEqual(self.out["balanced"]["label"], "벼 50% + 논콩 50%")

    def test_일하는_시간(self):
        self.assertEqual(self.o["벼 그대로"]["labor_h"], 83)
        self.assertEqual(self.o["논콩으로 모두 바꾸기"]["labor_h"], 136)


class 분석결과1_돈이_모자라는_달(unittest.TestCase):
    def test_물빠짐_나쁜_논_논콩은_10월에_617만원_먼저_씀(self):
        o = by_label(R["calc"](BAD_SOY))
        self.assertEqual((o["논콩 그대로"]["trough_month"], o["논콩 그대로"]["trough"]), ("10월", -617))
        self.assertEqual((o["벼로 모두 바꾸기"]["trough_month"], o["벼로 모두 바꾸기"]["trough"]), ("9월", -424))

    def test_시작자금_약_1320만_약_920만(self):
        o = by_label(R["calc"](BAD_SOY))
        self.assertEqual(round(o["논콩 그대로"]["need90"], -1), 1320)
        self.assertEqual(round(o["벼로 모두 바꾸기"]["need90"], -1), 920)

    def test_대금이_늦을수록_2월_200만원_못_모으는_경우_0_22_97(self):
        got = []
        for mode in ("once", "default", "late"):
            o = by_label(R["calc"]({**BAD_SOY, "pay_crop": SOY, "pay_mode": mode}))
            got.append(round(o["논콩 그대로"]["crop_short"] * 100))
        self.assertEqual(got, [0, 22, 97])

    def test_일손이_부족하면_물빠짐_나쁜_논_벼의_답이_벼_유지로(self):
        d = dict(drainage="나쁨", current="벼")
        self.assertEqual(R["calc"](d)["balanced"]["label"], "벼 70% + 들깨 30%")
        self.assertEqual(R["calc"]({**d, "labor": "부족"})["balanced"]["label"], "벼 그대로")


class 분석결과2_손해_보는_땅과_뒤집히는_조건(unittest.TestCase):
    def test_논_9가지_중_물빠짐_나쁜_3곳만_소득자료_1위와_다른_답(self):
        cells = R["grid"]({})["cells"]
        diff = sorted((c["water"], c["drainage"]) for c in cells if not c["same"])
        self.assertEqual(diff, [("관정", "나쁨"), ("수혜구역", "나쁨"), ("없음", "나쁨")])
        self.assertTrue(all(c["stat_best"] == "논콩" for c in cells))

    def test_물빠짐_나쁜_저수지_논_논콩은_벼보다_평균_54만_나쁜해_81만_덜(self):
        x = R["drainage"](dict(drainage="나쁨", current="벼"))
        bad = next(l for l in x["levels"] if l["level"] == "나쁨")
        soy = by_label(R["calc"](dict(drainage="나쁨", current="벼")))["논콩으로 모두 바꾸기"]
        self.assertEqual((bad["cur_mean"] - soy["mean"], bad["cur_bad20"] - soy["bad20"]), (54, 81))

    def test_배수_공사로_한해_98만원_약_7년(self):
        x = R["drainage"](BAD_SOY)
        good = next(l for l in x["levels"] if l["level"] == "좋음")
        self.assertEqual(good["cur_gain"], 98)
        self.assertEqual(round(good["cur_payback"]), 7)

    def test_답이_뒤집히는_조건(self):
        f = {x["cond"]: x["answer"] for x in R["flips"]({})["flips"]}
        self.assertEqual(f["논콩 값이 5% 떨어지면"], "벼 50% + 들깨 50%")
        self.assertEqual(f["처음 바꾸는 농가라 논콩 직불금을 못 받으면"], "벼 50% + 들깨 50%")
        self.assertEqual(f["벼 판매수입이 7% 이상 높으면"], "벼 그대로")

    def test_지금_작물_그대로가_추천일_때도_뒤집히는_조건을_찾음(self):
        # 관정 밭 고추는 '고추 그대로'가 추천. 아무 조건도 시험하지 않고 '답이 그대로'라고 하면 안 된다
        out = R["flips"](dict(land="밭", water="관정", current="고추", prev="없음"))
        self.assertEqual(out["base"], "고추 그대로")
        conds = [x for x in out["flips"] if x["changed"]]
        self.assertTrue(any(x["cond"].startswith("고추 판매수입이") for x in conds), out["flips"])

    def test_올해_조건_벼_7퍼센트_높으면_벼_그대로(self):
        self.assertEqual(R["calc"]({"rev_pct": {"벼": 7}})["balanced"]["label"], "벼 그대로")


class 분석결과3_가뭄과_큰비(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = R["climate"]({})

    def test_가문_7년_비많은_7년_표(self):
        rows = {r["name"]: (r["dry"], r["wet"], r["mean"], r["std"]) for r in self.c["hedge"]["rows"]}
        self.assertEqual(rows["벼만"], (475, 587, 541, 143))
        self.assertEqual(rows["논콩만"], (629, 460, 542, 107))
        self.assertEqual(rows["반반 섞기"], (552, 524, 541, 92))

    def test_섞으면_흔들림_14_36퍼센트_감소_나쁜해_31_56만원_증가(self):
        h = self.c["hedge"]
        self.assertEqual(sorted(round(x * 100) for x in h["std_cut"]), [14, 36])
        self.assertEqual(sorted(h["bad_gain"]), [31, 56])

    def test_큰비_온_해_76에서_87퍼센트(self):
        t = self.c["trend"]
        self.assertEqual((round(t["all"] * 100), round(t["recent"] * 100)), (76, 87))

    def test_물빠짐_나쁜_논_논콩_34년_487_최근15년_472(self):
        t = R["climate"](BAD_SOY)["trend"]
        self.assertEqual((t["cur_all"], t["cur_recent"]), (487, 472))

    def test_가뭄은_물_댈_곳이_없는_땅에_몰림(self):
        d = {x["land"]: x["dry"] for x in self.c["drought"]}
        self.assertEqual(d, {"저수지 논 (벼)": 0, "관정 논 (벼)": 0, "작은 관정 논 (벼, 하루 5mm)": 23,
                             "빗물 논 (논콩)": 12, "물 없는 밭 (참깨)": 9})

    def test_관정_논_벼를_논콩으로_지하수_약_7000톤_전기_약_2100kWh(self):
        w = self.c["water"]
        self.assertEqual((w["cur_mm"], w["alt_mm"]), (782, 85))
        self.assertEqual(round(w["tons"], -3), 7000)
        self.assertEqual(round(w["kwh"], -2), 2100)


class 분석결과4_농사_중과_재해_뒤(unittest.TestCase):
    def test_2026년_대표_농가_554에서_8월9일_572_10월13일_601(self):
        d = dict(alt=SOY, share=0.5)
        self.assertEqual(R["farm"]({**d, "today": "08-09"})["now"]["mid"], 572)
        f = R["farm"]({**d, "today": "10-13"})
        self.assertEqual((f["first"]["mid"], f["now"]["mid"]), (554, 601))

    def test_2020년_긴_장마_510에서_8월14일_256_수확무렵_204_실제값_290(self):
        d = {**BAD_SOY, "sown": {SOY: "06-15"}, "year": 2020}
        self.assertEqual(R["farm"]({**d, "today": "08-14"})["now"]["mid"], 256)
        f = R["farm"](d)
        self.assertEqual((f["first"]["mid"], f["now"]["mid"], f["actual"]), (510, 204, 290))

    def test_재해_뒤_7월14일_그대로두기_8월9일_되살리기(self):
        base = {**BAD_SOY, "crop": SOY, "sown": "06-15", "year": 2020}
        a = {o["name"]: o["mid"] for o in R["disaster"]({**base, "hit": "07-14"})["options"]}
        self.assertEqual((a["그대로 두기"], a["되살리기"], a["들깨 다시 심기"], a["갈아엎고 비워 두기"]), (395, 375, 204, -309))
        b = R["disaster"]({**base, "hit": "08-09"})
        m = {o["name"]: o["mid"] for o in b["options"]}
        self.assertEqual((m["그대로 두기"], m["되살리기"], m["갈아엎고 비워 두기"]), (241, 283, -351))
        self.assertEqual(b["best"], "되살리기")


class 입력_오류는_안내로(unittest.TestCase):
    """잘못된 입력에 서버 오류(500)가 아니라 고칠 내용을 알려 주는 400으로 답하는지 (HTTP 처리 단계)."""

    def test_숫자칸에_글자(self):
        code, out = http_util.run("calc", json.dumps({"area_py": "abc"}).encode())
        self.assertEqual(code, 400)
        self.assertIn("면적", out["error"])

    def test_UTF8이_아닌_본문(self):
        self.assertEqual(http_util.run("calc", "{\"current\": \"벼\"}".encode("cp949"))[0], 400)

    def test_없는_주소(self):
        self.assertEqual(http_util.run("nope", b"{}")[0], 404)

    def test_첫_해_1992년도_다시_계산됨(self):
        # 1992년은 앞선 해가 없어 '평년 비'를 낼 수 없다 → 오류 대신 빈 값
        code, out = http_util.run("farm", json.dumps({"year": 1992}).encode())
        self.assertEqual(code, 200, out)
        self.assertIsNone(out["crops"][0]["normal_rain"])

    def test_내_농장은_균형_추천을_스스로_골라_계산(self):
        # 첫 화면에서 calc 를 기다리지 않고 바로 부를 수 있게
        f = R["farm"]({"plan": "balanced", "today": "10-13"})
        self.assertEqual((f["label"], f["now"]["mid"]), ("벼 50% + 논콩 50%", 601))

    def test_날짜_안내는_0을_붙이지_않음(self):
        code, out = http_util.run("disaster", json.dumps({"hit": "11-20"}).encode())
        self.assertEqual(code, 400)
        self.assertIn("11월 5일", out["error"])

    def test_지금_작물이_논콩이어도_직불금_자격_없음이_적용됨(self):
        # GPT 검토 1번: 올해 처음 논콩을 심는 농가(작년 백태 직불 미이행)는 논콩 직불금(3,000평 200만 원)을 못 받는다
        base = by_label(R["calc"](dict(current=SOY)))["논콩 그대로"]["mean"]
        out = R["calc"](dict(current=SOY, no_subsidy=[SOY]))
        self.assertEqual(out["input"]["no_subsidy"], [SOY])
        self.assertEqual(base - by_label(out)["논콩 그대로"]["mean"], 200)

    def test_잘못된_자료형과_없는_날짜는_400(self):
        # GPT 검토 7번
        cases = [("calc", {"rev_pct": {"벼": "abc"}}), ("calc", {"rev_pct": [1, 2]}), ("calc", {"no_subsidy": "콩"}),
                 ("disaster", {"hit": "02-30"}), ("disaster", {"sown": "13-01"}), ("farm", {"today": "02-30"}),
                 ("farm", {"alt": "없는작물", "share": 1}), ("farm", {"sown": {"벼": "99-99"}}), ("calc", {"decision": "02-30"})]
        for name, body in cases:
            with self.subTest(name=name, body=body):
                code, out = http_util.run(name, json.dumps(body).encode())
                self.assertEqual(code, 400, out.get("error"))

    def test_밭에는_콩_직불금_없음이_적용되지_않음(self):
        out = R["calc"](dict(land="밭", water="관정", current="고추", prev="없음", no_subsidy=[SOY]))
        self.assertEqual(out["input"]["no_subsidy"], [])


if __name__ == "__main__":
    unittest.main()
