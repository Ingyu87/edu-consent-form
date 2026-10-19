#!/usr/bin/env python3
"""근거표 만들기: 동의서에 쓴 값마다 처리방침 원문 문장을 나란히 보여 줍니다. 파이썬 기본 기능만 사용.

사용:  python3 scripts/build_evidence.py data.json [저장할폴더]
결과:  근거표_<서비스이름>.md, 근거표_<서비스이름>.html (서비스마다)

JSON: services[] 안에 선택 항목
  "policy":   {"url": 처리방침 주소, "version": 시행일/버전, "checked": 확인한 날짜}
  "evidence": {"purpose"|"items"|"retention"|"recipient"|"overseas":
                 {"value": 동의서에 쓴 값, "quote": 처리방침 원문 문장, "note": 비고}}
원문 문장(quote)이 비어 있으면 그 줄은 [확인 필요]로 표시됩니다.
"""
from __future__ import annotations
import html, json, re, sys
from pathlib import Path

FIELDS = [("recipient", "운영사(제공받는 자)"), ("purpose", "수집·이용 목적"), ("items", "수집 항목"),
          ("retention", "보유 및 이용 기간"), ("overseas", "국외 이전")]
NEED = "[확인 필요]"

def default_value(s, key):
    c, t, o = s.get("collect") or {}, s.get("thirdParty") or {}, s.get("overseas")
    if key == "recipient": return t.get("recipient", "")
    if key == "overseas":
        return "없음" if not o else " / ".join(x for x in (o.get("recipient"), o.get("method"), o.get("items")) if x)
    return c.get(key, "")

def rows(s):
    ev = s.get("evidence") or {}
    out = []
    for key, label in FIELDS:
        e = ev.get(key) or {}
        value = re.sub(r"\*\*(.+?)\*\*", r"\1", str(e.get("value") or default_value(s, key)))
        quote = (e.get("quote") or "").strip()
        note = (e.get("note") or "").strip()
        if not quote:
            if key == "overseas" and not s.get("overseas"):
                note = note or "처리방침에서 국외 이전 내용을 찾지 못했습니다. 해외 회사·해외 서버가 아닌지 한 번 더 확인하세요."
            quote = NEED
        out.append((label, value, quote, note))
    return out

def safe_name(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "서비스"

def md_cell(x):
    return str(x).replace("|", "\\|").replace("\n", " ")

def to_md(s):
    p = s.get("policy") or {}
    lines = ["# 근거표: %s" % s.get("name", ""), "",
             "- 처리방침 주소: %s" % (p.get("url") or NEED),
             "- 처리방침 버전(시행일): %s" % (p.get("version") or NEED),
             "- 확인한 날짜: %s" % (p.get("checked") or NEED),
             "- 국외 이전 고지: %s" % ("넣음" if s.get("overseas") else "넣지 않음"), "",
             "| 항목 | 동의서에 쓴 값 | 처리방침 원문 | 비고 |", "|---|---|---|---|"]
    for r in rows(s):
        lines.append("| " + " | ".join(md_cell(x) for x in r) + " |")
    lines += ["", "배부 전에 처리방침 주소에서 최신 내용을 한 번 더 확인하세요. **[확인 필요]** 줄은 업체 처리방침이나 업체 문의로 채워 주세요.", ""]
    return "\n".join(lines)

CSS = """body{font-family:"함초롬돋움","HCR Dotum","맑은 고딕","Malgun Gothic","Noto Sans KR",sans-serif;margin:24px;color:#111;font-size:14px;line-height:1.55}
h1{font-size:19px;margin:0 0 10px} ul{margin:0 0 14px;padding-left:18px}
table{border-collapse:collapse;width:100%;max-width:980px;table-layout:fixed}
th,td{border:1px solid #999;padding:6px 8px;vertical-align:top;word-break:keep-all;overflow-wrap:anywhere}
th{background:#DFE6F7} col.a{width:15%} col.b{width:25%} col.c{width:38%} col.d{width:22%}
td.q{color:#333} .need{background:#fff3bf;outline:1px dashed #f59f00;font-weight:700}
p.tip{font-size:12.5px;color:#555;max-width:980px} @media print{.need{outline:none}}"""

def hl(text):
    return html.escape(text).replace(html.escape(NEED), '<span class="need">%s</span>' % html.escape(NEED))

def to_html(s):
    p = s.get("policy") or {}
    url = p.get("url")
    url_html = ('<a href="%s">%s</a>' % (html.escape(url), html.escape(url))) if url else hl(NEED)
    trs = "".join("<tr><th>%s</th><td>%s</td><td class=\"q\">%s</td><td>%s</td></tr>" % tuple(hl(x) for x in r) for r in rows(s))
    return ("<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>근거표: %s</title><style>%s</style></head><body><h1>근거표: %s</h1><ul>"
            "<li>처리방침 주소: %s</li><li>처리방침 버전(시행일): %s</li><li>확인한 날짜: %s</li><li>국외 이전 고지: %s</li></ul>"
            "<table><colgroup><col class=\"a\"><col class=\"b\"><col class=\"c\"><col class=\"d\"></colgroup>"
            "<thead><tr><th>항목</th><th>동의서에 쓴 값</th><th>처리방침 원문</th><th>비고</th></tr></thead><tbody>%s</tbody></table>"
            "<p class=\"tip\">배부 전에 처리방침 주소에서 최신 내용을 한 번 더 확인하세요. <span class=\"need\">[확인 필요]</span> 줄은 업체 처리방침이나 업체 문의로 채워 주세요.</p></body></html>"
            % (html.escape(s.get("name", "")), CSS, html.escape(s.get("name", "")), url_html,
               hl(p.get("version") or NEED), hl(p.get("checked") or NEED), "넣음" if s.get("overseas") else "넣지 않음", trs))

def main(src, outdir="."):
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    made = []
    for s in data.get("services") or []:
        base = "근거표_" + safe_name(s.get("name", ""))
        (out / (base + ".md")).write_text(to_md(s), encoding="utf-8")
        (out / (base + ".html")).write_text(to_html(s), encoding="utf-8")
        made += [str(out / (base + ".md")), str(out / (base + ".html"))]
    print("\n".join(made))

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("사용: python3 scripts/build_evidence.py data.json [저장할폴더]")
    main(*sys.argv[1:])
