#!/usr/bin/env python3
"""서울시교육청 공식 양식으로 '가정통신문 전체'(HWPX)를 만듭니다. 파이썬 기본 기능만 사용.

사용:  python3 scripts/build_letter.py data.json 가정통신문_개인정보동의서.hwpx

JSON (build_form.py / build_hwpx.py와 같은 services[] + 아래 선택 항목)
  "school":   학교 이름 (없으면 ○○초등학교)          → 맨 끝 '○○초등학교장 귀하'
  "deadline": 제출 기한 (없으면 OO월 OO일(요일))     → 인사말 '…까지 제출해 주시기 바랍니다'
  "date":     발송일 (없으면 양식 그대로 '2026.  .  .')

양식: assets/seoul-form/서울시교육청_AI에듀테크_동의안내_양식_20260305.hwpx
  (서울특별시교육청 창의미래교육과 「(서식) 개인정보 수집‧이용‧제공 동의 안내 양식(예시)」, 2026. 3. 5.)
동작: 앞쪽 '양식 안내' 쪽과 메모를 지우고, 제목·인사말·법적 근거·서명란은 양식 그대로 둡니다.
      구분 표는 양식 안의 예시 행(국외 이전 있는 행 / 없는 행)을 복제해 업체마다 한 행씩 채웁니다.
      글자 모양·문단 모양·테두리는 모두 양식에 이미 있는 것을 씁니다(빨간 안내 글씨는 검정으로).
"""
from __future__ import annotations
import copy, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FORM = HERE / "assets" / "seoul-form" / "서울시교육청_AI에듀테크_동의안내_양식_20260305.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
q = lambda t: "{%s}%s" % (HP, t)

# 양식 header.xml 안의 글자 모양 번호 (양식에서 확인한 값)
CP = dict(plain=17, bold=18, purpose=19, label=24, u12=23, u11=65, name=16)

def _ns(xml: str):
    for pfx, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', xml[:5000]):
        ET.register_namespace(pfx, uri)

def text_of(el):
    return "".join(t.text or "" for t in el.iter(q("t")))

def strip_memos(root):
    """메모(fieldBegin type=MEMO … fieldEnd)가 들어 있는 ctrl을 지웁니다."""
    memo_ids = set()
    for run in root.iter(q("run")):
        for ctrl in list(run.findall(q("ctrl"))):
            fb = ctrl.find(q("fieldBegin"))
            fe = ctrl.find(q("fieldEnd"))
            if fb is not None and fb.get("type") == "MEMO":
                memo_ids.add(fb.get("id")); run.remove(ctrl)
            elif fe is not None and (fe.get("beginIDRef") in memo_ids or not fe.get("beginIDRef")):
                run.remove(ctrl)
    # 뒤에 남은 fieldEnd(앞에서 id를 못 본 경우)
    for run in root.iter(q("run")):
        for ctrl in list(run.findall(q("ctrl"))):
            fe = ctrl.find(q("fieldEnd"))
            if fe is not None and fe.get("beginIDRef") in memo_ids:
                run.remove(ctrl)

def drop_lineseg(p):
    for ls in p.findall(q("linesegarray")):
        p.remove(ls)

def set_runs(p, runs):
    """문단 p의 글자를 runs[(charPr, text)]로 바꿉니다(문단 모양은 그대로)."""
    for r in list(p.findall(q("run"))):
        p.remove(r)
    drop_lineseg(p)
    for cp, t in runs:
        r = ET.SubElement(p, q("run"), {"charPrIDRef": str(cp)})
        ET.SubElement(r, q("t")).text = t
    # run 뒤에 linesegarray가 오도록(없으면 한글이 다시 계산)
    return p

def md(text, base, bold):
    out = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", str(text or ""))):
        if part:
            out.append((bold if i % 2 else base, part))
    return out or [(base, "")]

def replace_text(p, old, new):
    for t in p.iter(q("t")):
        if t.text and old in t.text:
            t.text = t.text.replace(old, new); return True
    return False

def build(data: dict, out: Path) -> Path:
    services = data.get("services") or []
    if not services:
        raise SystemExit("services 배열이 비어 있습니다")
    school = data.get("school") or "○○초등학교"
    deadline = data.get("deadline") or "OO월 OO일(요일)"
    date = data.get("date")

    z = zipfile.ZipFile(FORM)
    files = {n: z.read(n) for n in z.namelist()}
    sec_xml = files["Contents/section0.xml"].decode("utf-8")
    root_open = re.match(r"<\?xml[^>]*\?>\s*(<hs:sec[^>]*>)", sec_xml).group(1)
    _ns(sec_xml)
    root = ET.fromstring(sec_xml)
    strip_memos(root)
    paras = root.findall(q("p"))

    # 1) 첫 문단: 용지 설정(secPr/colPr)만 남기고 '양식 안내' 표 삭제
    first = paras[0]
    for run in first.findall(q("run")):
        for ch in list(run):
            if ch.tag == q("tbl"):
                run.remove(ch)
    drop_lineseg(first)

    # 2) 제목의 '(예시)' 삭제
    for t in paras[1].iter(q("t")):
        if t.text and "(예시)" in t.text:
            t.text = t.text.replace("(예시)", "")
    # 3) 제출 기한, 날짜, 학교장
    for p in paras:
        s = text_of(p)
        if "OO월 OO일(요일)" in s:
            if not replace_text(p, "OO월 OO일(요일)", deadline):
                # 여러 run으로 나뉜 경우: 'OO월 OO일(요일)' 조각이 든 run들을 합쳐 바꿈
                ts = [t for t in p.iter(q("t")) if t.text]
                joined = "".join(t.text for t in ts)
                i = joined.find("OO월 OO일(요일)")
                pos = 0
                for t in ts:
                    a, b = pos, pos + len(t.text); pos = b
                    if b <= i or a >= i + len("OO월 OO일(요일)"):
                        continue
                    keep_l = t.text[: max(0, i - a)]
                    keep_r = t.text[max(0, i + len("OO월 OO일(요일)") - a):]
                    t.text = keep_l + (deadline if a <= i < b else "") + keep_r
        if s.strip().startswith("○○학교장"):
            replace_text(p, "○○학교장", school + "장")
        if date and re.fullmatch(r"\s*2026\.\s*\.\s*\.\s*", s):
            for t in p.iter(q("t")):
                if t.text and "2026." in t.text:
                    t.text = date
                else:
                    t.text = "" if t.text else t.text

    # 4) 구분 표
    tbl = next(t for t in root.iter(q("tbl")) if "구분" in text_of(t) and "에듀테크" in text_of(t))
    rows = tbl.findall(q("tr"))
    cell = lambda tr, col: next(tc for tc in tr.findall(q("tc")) if tc.find(q("cellAddr")).get("colAddr") == str(col))
    # 예시 행: A(국외 이전 있음) = 1,2,3행 / B(없음) = 4,5행
    A_name, A_col, A_third, A_over = cell(rows[1], 0), cell(rows[1], 1), cell(rows[2], 1), cell(rows[3], 1)
    B_name, B_col, B_third = cell(rows[4], 0), cell(rows[4], 1), cell(rows[5], 1)
    bf = lambda tc: tc.get("borderFillIDRef")
    for tr in rows[1:]:
        tbl.remove(tr)

    def fill_collect(proto, c):
        tc = copy.deepcopy(proto)
        ps = tc.find(q("subList")).findall(q("p"))
        set_runs(ps[0], [(CP["plain"], "1. "), (CP["bold"], "수집·이용 목적"), (CP["plain"], ": ")] + md(c.get("purpose"), CP["purpose"], CP["bold"]))
        set_runs(ps[1], [(CP["plain"], "2. "), (CP["bold"], "수집 항목"), (CP["plain"], ": ")] + md(c.get("items"), CP["plain"], CP["bold"]))
        set_runs(ps[2], [(CP["plain"], "3. "), (CP["bold"], "보유 및 이용 기간: ")] + md(c.get("retention"), CP["u12"], CP["u12"]))
        for p in ps[3:]:
            drop_lineseg(p)   # 4. 동의 거부 문구, 동의 상자는 양식 그대로
        return tc

    def fill_third(proto, t):
        tc = copy.deepcopy(proto)
        ps = tc.find(q("subList")).findall(q("p"))
        set_runs(ps[0], [(CP["bold"], "◆ 개인정보의 제3자 제공 고지")])
        set_runs(ps[1], [(CP["plain"], "1. "), (CP["label"], "개인정보를 제공받는 자"), (CP["plain"], ": ")] + md(t.get("recipient"), CP["plain"], CP["bold"]))
        set_runs(ps[2], [(CP["plain"], "2. "), (CP["label"], "제공받는 자의 이용 목적"), (CP["plain"], ": ")] + md(t.get("purpose"), CP["u11"], CP["u11"]))
        set_runs(ps[3], [(CP["plain"], "3. "), (CP["bold"], "제공하는 개인정보 항목"), (CP["plain"], ": ")] + md(t.get("items"), CP["plain"], CP["bold"]))
        set_runs(ps[4], [(CP["plain"], "4. "), (CP["label"], "제공받는 자의 보유 및 이용기간"), (CP["plain"], ": ")] + md(t.get("retention"), CP["u12"], CP["u12"]))
        return tc

    def fill_over(proto, o):
        tc = copy.deepcopy(proto)
        ps = tc.find(q("subList")).findall(q("p"))
        set_runs(ps[0], [(CP["bold"], "◆ 개인정보 국외 이전 고지")])
        set_runs(ps[1], [(CP["bold"], "1. 개인정보를 이전받는 자 : ")] + md(o.get("recipient"), CP["plain"], CP["bold"]))
        set_runs(ps[2], [(CP["bold"], "2. 이전되는 국가, 시기 및 방법 : ")] + md(o.get("method"), CP["plain"], CP["bold"]))
        set_runs(ps[3], [(CP["bold"], "3. 이전되는 개인정보 항목 : ")] + md(o.get("items"), CP["plain"], CP["bold"]))
        set_runs(ps[4], [(CP["bold"], "4. 보유 및 이용 기간 : ")] + md(o.get("retention"), CP["u12"], CP["u12"]))
        return tc

    r = 1
    total_h = int(rows[0].find(q("tc")).find(q("cellSz")).get("height"))
    for si, s in enumerate(services):
        c, t, o = s.get("collect") or {}, s.get("thirdParty") or {}, s.get("overseas")
        blocks = [fill_collect(A_col if si == 0 else B_col, c),
                  fill_third(A_third if o else B_third, t)]
        if o:
            blocks.append(fill_over(A_over, o))
        name = copy.deepcopy(A_name if si == 0 else B_name)
        set_runs(name.find(q("subList")).find(q("p")), md(s.get("name"), CP["name"], CP["bold"]))
        # 테두리: 첫 업체 위는 머리행 이중선(0.5mm), 그 다음 업체 위는 0.7mm 이중선
        blocks[0].set("borderFillIDRef", bf(A_col) if si == 0 else bf(B_col))
        name.set("borderFillIDRef", bf(A_name) if si == 0 else bf(B_name))
        name.find(q("cellSpan")).set("rowSpan", str(len(blocks)))
        h_sum = 0
        for bi, tc in enumerate(blocks):
            tc.find(q("cellAddr")).set("rowAddr", str(r + bi))
            h_sum += int(tc.find(q("cellSz")).get("height"))
        name.find(q("cellAddr")).set("rowAddr", str(r))
        name.find(q("cellSz")).set("height", str(h_sum))
        for bi, tc in enumerate(blocks):
            tr = ET.SubElement(tbl, q("tr"))
            if bi == 0:
                tr.append(name)
            tr.append(tc)
        r += len(blocks); total_h += h_sum
    tbl.set("rowCnt", str(r))
    tbl.find(q("sz")).set("height", str(total_h))
    # 표가 들어 있는 문단의 줄 정보는 다시 계산하도록
    for p in paras:
        if any(x is tbl for x in p.iter(q("tbl"))):
            drop_lineseg(p)

    body = ET.tostring(root, encoding="unicode")
    body = re.sub(r"^<hs:sec[^>]*>", root_open, body, count=1)
    files["Contents/section0.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + body).encode("utf-8")
    title = "AI 및 에듀테크 활용 교육을 위한 개인정보 수집·이용·제공 동의 안내"
    hpf = files["Contents/content.hpf"].decode("utf-8")
    hpf = re.sub(r"<opf:title>[^<]*</opf:title>", "<opf:title>%s</opf:title>" % title, hpf)
    files["Contents/content.hpf"] = hpf.encode("utf-8")
    prev = [title, school] + [s.get("name", "") for s in services]
    files["Preview/PrvText.txt"] = "\n".join(prev).encode("utf-8")
    files.pop("Preview/PrvImage.png", None)

    out.parent.mkdir(parents=True, exist_ok=True)
    order = ["mimetype"] + [n for n in files if n != "mimetype"]
    with zipfile.ZipFile(out, "w") as zo:
        for n in order:
            ct = zipfile.ZIP_STORED if n in ("mimetype", "version.xml") else zipfile.ZIP_DEFLATED
            zo.writestr(zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0)), files[n], compress_type=ct)
    check(out)
    return out

def check(path: Path):
    from xml.dom import minidom
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert names[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        for n in names:
            if n.endswith((".xml", ".hpf", ".rdf")):
                minidom.parseString(z.read(n))
        hdr = z.read("Contents/header.xml").decode("utf-8"); sec = z.read("Contents/section0.xml").decode("utf-8")
        for kind, tag in (("charPr", "charPrIDRef"), ("paraPr", "paraPrIDRef"), ("borderFill", "borderFillIDRef")):
            ids = set(re.findall(r'<hh:%s id="(\d+)"' % kind, hdr))
            missing = set(re.findall(r'%s="(\d+)"' % tag, sec)) - ids
            assert not missing, "%s 정의 없음: %s" % (kind, missing)
        assert "MEMO" not in sec, "메모가 남아 있습니다"

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("사용: python3 scripts/build_letter.py data.json 가정통신문_개인정보동의서.hwpx")
    print(build(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2])))
