#!/usr/bin/env python3
"""데이터(JSON)를 assets/template.html에 넣어 동의서 표 HTML을 만듭니다.
사용: python3 scripts/build_form.py data.json 결과.html
외부 패키지 필요 없음. 파이썬이 없으면 template.html의 consent-data JSON 블록만 직접 바꿔도 됩니다."""
import json, re, sys, pathlib
here = pathlib.Path(__file__).resolve().parent.parent
src, out = sys.argv[1], sys.argv[2]
data = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
assert data.get("services"), "services 배열이 비어 있습니다"
tpl = (here / "assets" / "template.html").read_text(encoding="utf-8")
blob = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
html, n = re.subn(r'(<script id="consent-data" type="application/json">)(.*?)(</script>)',
                  lambda m: m.group(1) + "\n" + blob + "\n" + m.group(3), tpl, count=1, flags=re.S)
assert n == 1, "템플릿에서 consent-data 블록을 찾지 못했습니다"
pathlib.Path(out).write_text(html, encoding="utf-8")
print(out)
