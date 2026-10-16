import re
path = "services/flight_service.py"
s = open(path, "r", encoding="utf-8").read()

# 1. Remove the whole "Options builder" section: from the header comment
#    above DEFAULT_FLIGHT_MARKUP_PCT through the end of flight_options_for_package.
start_marker = "# ── Options builder for the package detail page ─────────────────────"
end_marker = '__all__ = ['

if start_marker in s and end_marker in s:
    i = s.index(start_marker)
    j = s.index(end_marker)
    s = s[:i] + s[j:]
    print("removed options builder block")
else:
    print("markers not found — aborting")
    raise SystemExit(1)

# 2. Drop flight_options_for_package from __all__
s = s.replace('    "flight_options_for_package",\n', '')

# 3. Remove the two docstring mentions in the module docstring
s = s.replace(
    "    flight_options_for_package(package, check_in, check_out,\n"
    "                               passengers=1, land_total=None, ...)\n"
    "        -> list[dict]  (option cards for the package detail page, one per airline,\n"
    "                        with land + flight + markup + transfer baked into grand_total)\n",
    "",
)
s = s.replace(
    "* flight_options_for_package picks the CLOSEST date first, then\n"
    "  cheapest as a tiebreaker — so a user asking for 1 Nov gets 1 Nov\n"
    "  if it exists, even if a cheaper flight is available on 4 Nov.\n",
    "",
)

open(path, "w", encoding="utf-8").write(s)
print("flight_service.py patched")