import pathlib, re
p = pathlib.Path("templates/base.html")
s = p.read_text(encoding="utf-8")
new_s = re.sub(r"(css/eltut\.css'\) \}\}\?v=)\d+", r"\g<1>11", s)
if new_s != s:
    p.write_text(new_s, encoding="utf-8")
    print("base.html: bumped to v=11")
else:
    print("no version bump needed")
