# Find the app factory
s = open("app.py", encoding="utf-8").read()
if "after_request" in s and "Cache-Control" in s:
    print("already has after_request cache control")
else:
    print("no after_request cache control found")
