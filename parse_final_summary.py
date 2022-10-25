#!/usr/bin/env python3

# Very basic wrapper to hesiod.load_final_summary()

import sys
from hesiod import load_final_summary, dump_yaml

print(dump_yaml(load_final_summary(str(sys.argv[1]))), end='')
