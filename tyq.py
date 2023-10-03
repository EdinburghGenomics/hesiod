#!/usr/bin/env python3

"""Quickly get a value out of a YAML file.

   Turns out the "yq" command line tool is sucky. So here is "tyq" aka Tim's YAML Query-er
   It's REALLY basic. But it works.

   tyq.py '{key}' file.yaml
"""

import sys
import yaml

def main(query, yaml_file="-"):

    if yaml_file == "-":
        ydata = yaml.safe_load(sys.stdin)
    else:
        with open(yaml_file) as yfh:
            ydata = yaml.safe_load(yfh)

    if isinstance(ydata, list):
        print(query.format(*ydata))
    else:
        try:
            # Normal case. Entire dict is in {0} or you can give a top
            # level key as {key}
            print(query.format(ydata, **ydata))
        except TypeError:
            print(query.format(ydata))

if __name__ == "__main__":
    main(*sys.argv[1:])

