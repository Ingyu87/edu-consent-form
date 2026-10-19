#!/usr/bin/env python3
"""데이터(JSON)로 한글(HWPX) 동의서 표를 만듭니다. 파이썬 기본 기능만 사용(설치 필요 없음).

사용:  python3 scripts/build_hwpx.py data.json 개인정보동의서_서비스이름.hwpx

JSON 모양은 build_form.py(HTML)와 같습니다.
  {"services":[{"name":..., "collect":{purpose,items,retention},
                "thirdParty":{recipient,purpose,items,retention},
                "overseas":{recipient,method,items,retention} 또는 null}]}
값 안의 **글자** 는 굵게 처리됩니다.

서식(원본 가정통신문 실측, references/style-spec.md):
  글꼴 함초롬돋움 / 본문 10pt / 머리행 13pt 굵게 + 배경 #DFE6F7 / 보유기간 값 12pt 굵게 밑줄 /
  3자 이용목적 값 11pt 굵게 밑줄 / 국외 이전 방법 값 빨강 / 동의 줄은 #DFE6F7 상자(표 안의 표) /
  선: 머리행 위 0.4mm 실선·아래 0.5mm 이중선, 업체 사이 0.7mm 이중선, 칸 안 구역 사이 0.12mm 실선(국외 이전 앞은 이중선)
"""
from __future__ import annotations
import datetime, json, re, sys, zipfile
from pathlib import Path
from xml.dom import minidom
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent.parent
SKEL = HERE / "assets" / "hwpx-skeleton"

REFUSE = ("4. 개인정보 수집․이용에 대한 동의를 거부할 수 있습니다. 동의를 거부할 경우 해당 에듀테크를 "
          "활용한 맞춤형 학습 지원 및 수업 활동 참여가 제한될 수 있습니다.")
AGREE = "개인정보 수집·이용에  □ 동의합니다.    □ 동의하지 않습니다."
HEAD_FILL = "#DFE6F7"
COL_W = (7000, 41700)          # 구분 70pt + 고지 417pt (HWPUNIT, 1pt = 100)
CELL_M = (510, 510, 141, 141)  # 칸 안 여백 좌·우·위·아래
LINE = 1300                    # 10pt × 130%

# ---------------------------------------------------------------- 머리(header.xml) 꾸미기
class Header:
    def __init__(self, xml: str):
        self.xml = xml
        self.cp_tpl = re.search(r'<hh:charPr id="0".*?</hh:charPr>', xml, re.S).group(0)
        self.pp_tpl = re.search(r'<hh:paraPr id="0".*?</hh:paraPr>', xml, re.S).group(0)
        self.cp_next = self._count("charProperties")
        self.pp_next = self._count("paraProperties")
        self.bf_next = self._count("borderFills") + 1   # borderFill id는 1부터
        self.cps, self.pps, self.bfs = {}, {}, {}
        self.new_cp, self.new_pp, self.new_bf = [], [], []

    def _count(self, tag):
        return int(re.search(r'<hh:%s itemCnt="(\d+)"' % tag, self.xml).group(1))

    def char(self, size=10, bold=False, underline=False, color="#000000"):
        key = (size, bold, underline, color)
        if key not in self.cps:
            x = self.cp_tpl.replace('id="0"', 'id="%d"' % self.cp_next, 1)
            x = re.sub(r'height="\d+"', 'height="%d"' % (size * 100), x, count=1)
            x = re.sub(r'textColor="[^"]+"', 'textColor="%s"' % color, x, count=1)
            x = re.sub(r'<hh:fontRef [^>]*/>', '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>', x)
            x = x.replace("<hh:bold/>", "")
            ul = '<hh:underline type="%s" shape="SOLID" color="#000000"/>' % ("BOTTOM" if underline else "NONE")
            x = re.sub(r'<hh:underline [^>]*/>', ("<hh:bold/>" if bold else "") + ul, x)
            self.new_cp.append(x); self.cps[key] = self.cp_next; self.cp_next += 1
        return self.cps[key]

    def para(self, align="JUSTIFY", hang=0, line=130):
        key = (align, hang, line)
        if key not in self.pps:
            x = self.pp_tpl.replace('id="0"', 'id="%d"' % self.pp_next, 1)
            x = re.sub(r'<hh:align horizontal="\w+"', '<hh:align horizontal="%s"' % align, x)
            x = x.replace('breakNonLatinWord="KEEP_WORD"', 'breakNonLatinWord="BREAK_WORD"')
            case, default = re.search(r'(<hp:case.*?</hp:case>)(<hp:default>.*?</hp:default>)', x, re.S).groups()
            def fix(s, k):  # hp:case = HWPUNIT, hp:default = 2배 값 (한글 저장 방식과 같게)
                s = re.sub(r'<hc:intent value="-?\d+"', '<hc:intent value="%d"' % (-hang * k), s)
                return re.sub(r'<hh:lineSpacing type="PERCENT" value="\d+"', '<hh:lineSpacing type="PERCENT" value="%d"' % line, s)
            x = x.replace(case, fix(case, 1)).replace(default, fix(default, 2))
            self.new_pp.append(x); self.pps[key] = self.pp_next; self.pp_next += 1
        return self.pps[key]

    def border(self, left, right, top, bottom, fill=None):
        """각 변 = ("NONE"|"SOLID"|"DOUBLE_SLIM", "0.12 mm")"""
        key = (left, right, top, bottom, fill)
        if key not in self.bfs:
            def side(n, s):
                return '<hh:%sBorder type="%s" width="%s" color="#000000"/>' % (n, s[0], s[1])
            x = ('<hh:borderFill id="%d" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
                 '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
                 % self.bf_next + side("left", left) + side("right", right) + side("top", top) + side("bottom", bottom) +
                 '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>')
            if fill:
                x += '<hc:fillBrush><hc:winBrush faceColor="%s" hatchColor="#000000" alpha="0"/></hc:fillBrush>' % fill
            x += "</hh:borderFill>"
            self.new_bf.append(x); self.bfs[key] = self.bf_next; self.bf_next += 1
        return self.bfs[key]

    def render(self):
        x = self.xml
        for tag, close, items, cnt in (("borderFills", "</hh:borderFills>", self.new_bf, self.bf_next - 1),
                                       ("charProperties", "</hh:charProperties>", self.new_cp, self.cp_next),
                                       ("paraProperties", "</hh:paraProperties>", self.new_pp, self.pp_next)):
            x = x.replace(close, "".join(items) + close, 1)
            x = re.sub(r'<hh:%s itemCnt="\d+"' % tag, '<hh:%s itemCnt="%d"' % (tag, cnt), x, count=1)
        return x

# ---------------------------------------------------------------- 본문 만들기
NONE = ("NONE", "0.12 mm"); THIN = ("SOLID", "0.12 mm"); TOP = ("SOLID", "0.4 mm")
DBL_HEAD = ("DOUBLE_SLIM", "0.5 mm"); DBL_ROW = ("DOUBLE_SLIM", "0.7 mm"); DBL_IN = ("DOUBLE_SLIM", "0.5 mm")
_ids = iter(range(1900000000, 2000000000))

def runs(H, text, base, bold_variant):
    """**굵게** 표시를 run 목록으로."""
    out = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", str(text or ""))):
        if part:
            out.append((bold_variant if i % 2 else base, part))
    return out or [(base, "")]

def para(pid, rs):
    body = "".join('<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>' % (c, escape(t)) for c, t in rs)
    return '<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">%s</hp:p>' % (pid, body)

def est_lines(rs, width_chars=48):  # 칸 높이는 최소값이라 조금 작게 잡음(한글이 내용에 맞게 늘림)
    n = sum(len(t) for _, t in rs)
    return max(1, -(-n // width_chars))

def cell(r, c, w, h, bf, paras, valign="TOP", rowspan=1, header=False):
    return ('<hp:tc name="" header="%d" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="%d">'
            '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="%s" linkListIDRef="0" '
            'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">%s</hp:subList>'
            '<hp:cellAddr colAddr="%d" rowAddr="%d"/><hp:cellSpan colSpan="1" rowSpan="%d"/>'
            '<hp:cellSz width="%d" height="%d"/><hp:cellMargin left="%d" right="%d" top="%d" bottom="%d"/></hp:tc>'
            % ((1 if header else 0), bf, valign, "".join(paras), c, r, rowspan, w, h, *CELL_M))

def table(rows_xml, nrows, ncols, width, height, bf, inline):
    return ('<hp:tbl id="%d" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
            'dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="%d" colCnt="%d" cellSpacing="0" '
            'borderFillIDRef="%d" noAdjust="0"><hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="%d" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
            'vertRelTo="PARA" horzRelTo="%s" vertAlign="TOP" horzAlign="%s" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="%d" right="%d" top="%d" bottom="%d"/>%s</hp:tbl>'
            % (next(_ids), nrows, ncols, bf, width, height, 1 if inline else 0,
               "PARA" if inline else "COLUMN", "CENTER" if inline else "LEFT", *CELL_M, rows_xml))

def build(data: dict) -> tuple[str, str, str]:
    H = Header((SKEL / "header.xml").read_text(encoding="utf-8"))
    R10, B10, B13 = H.char(10), H.char(10, True), H.char(13, True)
    BU12, BU11 = H.char(12, True, True), H.char(11, True, True)
    RED, REDB = H.char(10, False, False, "#FF0000"), H.char(10, True, False, "#FF0000")
    P_ITEM = H.para("JUSTIFY", 1400)       # 번호 뒤 내어쓰기 14pt
    P_PURP = H.para("JUSTIFY", 8960)       # 1. 수집·이용 목적: 값 시작에 맞춤
    P_CENTER = H.para("CENTER", 0)
    P_LEFT = H.para("JUSTIFY", 0)
    bf_tbl = H.border(NONE, NONE, NONE, NONE)
    bf_agree = H.border(THIN, THIN, THIN, THIN, HEAD_FILL)
    services = data.get("services") or []
    if not services:
        raise SystemExit("services 배열이 비어 있습니다")

    rows, preview, r = [], [], 0
    # 머리행
    rows.append("<hp:tr>" +
        cell(0, 0, COL_W[0], 1850, H.border(NONE, THIN, TOP, DBL_HEAD, HEAD_FILL), [para(P_CENTER, [(B13, "구분")])], "CENTER", header=True) +
        cell(0, 1, COL_W[1], 1850, H.border(THIN, NONE, TOP, DBL_HEAD, HEAD_FILL),
             [para(P_CENTER, [(B13, "개인정보 수집·이용·제공 동의 및 제3자 제공 등 고지")])], "CENTER", header=True) + "</hp:tr>")
    preview.append("구분 | 개인정보 수집·이용·제공 동의 및 제3자 제공 등 고지")
    r = 1
    for si, s in enumerate(services):
        c, t, o = s.get("collect") or {}, s.get("thirdParty") or {}, s.get("overseas")
        blocks = []
        # 1) 수집·이용 + 동의 상자
        agree_cell = cell(0, 0, 40200, 1950, bf_agree, [para(P_CENTER, [(B10, AGREE)])], "CENTER")
        agree_tbl = table("<hp:tr>%s</hp:tr>" % agree_cell, 1, 1, 40200, 1950, bf_tbl, True)
        lines = [
            (P_PURP, [(R10, "1. "), (B10, "수집·이용 목적"), (R10, ": ")] + runs(H, c.get("purpose"), R10, B10)),
            (P_ITEM, [(R10, "2. "), (B10, "수집 항목"), (R10, ": ")] + runs(H, c.get("items"), R10, B10)),
            (P_ITEM, [(R10, "3. "), (B10, "보유 및 이용 기간: ")] + runs(H, c.get("retention"), BU12, BU12)),
            (P_ITEM, [(R10, REFUSE)]),
        ]
        ps = [para(p, rs) for p, rs in lines]
        ps.append('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                  '<hp:run charPrIDRef="%d">%s<hp:t/></hp:run></hp:p>' % (P_CENTER, R10, agree_tbl))
        blocks.append((ps, sum(est_lines(rs) for _, rs in lines) * LINE + 1900, "collect"))
        # 2) 제3자 제공
        lines = [
            (P_LEFT, [(B10, "◆ 개인정보의 제3자 제공 고지")]),
            (P_ITEM, [(R10, "1. "), (B10, "개인정보를 제공받는 자"), (R10, ": ")] + runs(H, t.get("recipient"), R10, B10)),
            (P_ITEM, [(R10, "2. "), (B10, "제공받는 자의 이용 목적"), (R10, ": ")] + runs(H, t.get("purpose"), BU11, BU11)),
            (P_ITEM, [(R10, "3. "), (B10, "제공하는 개인정보 항목"), (R10, ": ")] + runs(H, t.get("items"), R10, B10)),
            (P_ITEM, [(R10, "4. "), (B10, "제공받는 자의 보유 및 이용기간"), (R10, ": ")] + runs(H, t.get("retention"), BU12, BU12)),
        ]
        blocks.append(([para(p, rs) for p, rs in lines], sum(est_lines(rs) for _, rs in lines) * LINE + 282, "third"))
        # 3) 국외 이전 (있을 때만)
        if o:
            lines = [
                (P_LEFT, [(B10, "◆ 개인정보 국외 이전 고지")]),
                (P_ITEM, [(B10, "1. 개인정보를 이전받는 자 : ")] + runs(H, o.get("recipient"), B10, B10)),
                (P_ITEM, [(B10, "2. 이전되는 국가, 시기 및 방법 : ")] + runs(H, o.get("method"), RED, REDB)),
                (P_ITEM, [(B10, "3. 이전되는 개인정보 항목 : ")] + runs(H, o.get("items"), B10, B10)),
                (P_ITEM, [(B10, "4. 보유 및 이용 기간 : ")] + runs(H, o.get("retention"), BU12, BU12)),
            ]
            blocks.append(([para(p, rs) for p, rs in lines], sum(est_lines(rs) for _, rs in lines) * LINE + 282, "overseas"))

        top_row = DBL_HEAD if si == 0 else DBL_ROW
        k = len(blocks)
        total_h = sum(h for _, h, _ in blocks)
        name_cell = cell(r, 0, COL_W[0], total_h, H.border(NONE, THIN, top_row, DBL_ROW),
                         [para(P_CENTER, runs(H, s.get("name"), R10, B10))], "CENTER", rowspan=k)
        for bi, (ps, h, kind) in enumerate(blocks):
            top = top_row if bi == 0 else (DBL_IN if kind == "overseas" else THIN)
            nxt = blocks[bi + 1][2] if bi + 1 < k else None
            bottom = DBL_ROW if nxt is None else (DBL_IN if nxt == "overseas" else THIN)
            bf = H.border(THIN, NONE, top, bottom)
            rows.append("<hp:tr>" + (name_cell if bi == 0 else "") + cell(r, 1, COL_W[1], h, bf, ps) + "</hp:tr>")
            r += 1
        preview.append("%s | %s" % (s.get("name", ""), c.get("purpose", "")))

    main = table("".join(rows), r, 2, sum(COL_W), 1850 + 9000 * len(services), bf_tbl, False)
    secpr = (SKEL / "secpr.xml").read_text(encoding="utf-8")
    section = ((SKEL / "section-open.xml").read_text(encoding="utf-8") +
               '<hp:p id="0" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
               '<hp:run charPrIDRef="%d">%s</hp:run><hp:run charPrIDRef="%d">%s<hp:t/></hp:run></hp:p>'
               '<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
               '<hp:run charPrIDRef="%d"/></hp:p></hs:sec>'
               % (P_LEFT, R10, secpr, R10, main, P_LEFT, R10))
    return H.render(), section, "\n".join(preview)

def save(data: dict, out: Path) -> Path:
    header, section, preview = build(data)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hpf = (SKEL / "content.hpf").read_text(encoding="utf-8").replace("{TITLE}", "개인정보 수집·이용·제공 동의서").replace("{DATE}", now)
    files = [
        ("mimetype", b"application/hwp+zip", zipfile.ZIP_STORED),
        ("version.xml", (SKEL / "version.xml").read_bytes(), zipfile.ZIP_STORED),
        ("Contents/header.xml", header.encode("utf-8"), zipfile.ZIP_DEFLATED),
        ("Contents/section0.xml", section.encode("utf-8"), zipfile.ZIP_DEFLATED),
        ("Contents/content.hpf", hpf.encode("utf-8"), zipfile.ZIP_DEFLATED),
        ("Preview/PrvText.txt", preview[:1000].encode("utf-8"), zipfile.ZIP_DEFLATED),
        ("settings.xml", (SKEL / "settings.xml").read_bytes(), zipfile.ZIP_DEFLATED),
        ("META-INF/container.rdf", (SKEL / "META-INF/container.rdf").read_bytes(), zipfile.ZIP_DEFLATED),
        ("META-INF/container.xml", (SKEL / "META-INF/container.xml").read_bytes(), zipfile.ZIP_DEFLATED),
        ("META-INF/manifest.xml", (SKEL / "META-INF/manifest.xml").read_bytes(), zipfile.ZIP_DEFLATED),
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:   # mimetype이 맨 앞, 압축 없이
        for name, data_, ct in files:
            z.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data_, compress_type=ct)
    check(out)
    return out

def check(path: Path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert names[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED, "mimetype 오류"
        assert z.read("mimetype") == b"application/hwp+zip"
        for n in names:
            if n.endswith((".xml", ".hpf", ".rdf")):
                minidom.parseString(z.read(n))   # XML 형식 검사
        hdr = z.read("Contents/header.xml").decode("utf-8"); sec = z.read("Contents/section0.xml").decode("utf-8")
        for kind, tag in (("charPr", "charPrIDRef"), ("paraPr", "paraPrIDRef"), ("borderFill", "borderFillIDRef")):
            ids = set(re.findall(r'<hh:%s id="(\d+)"' % kind, hdr))
            used = set(re.findall(r'%s="(\d+)"' % tag, sec))
            missing = used - ids
            assert not missing, "%s 정의 없음: %s" % (kind, missing)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("사용: python3 scripts/build_hwpx.py data.json 결과.hwpx")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(save(data, Path(sys.argv[2])))
