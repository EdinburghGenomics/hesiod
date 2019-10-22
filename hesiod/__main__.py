# If called as "python3 -m hesiod" report the version.
# But it turns out I still need hesiod_version.py

from . import hesiod_version

print("Hesiod v{}".format(hesiod_version))
