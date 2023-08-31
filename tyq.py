#!/usr/bin/env python3

# Turns out the "yq" command line tool is sucky. So here is "tyq" aka Tim's YAML Query-er
# It's REALLY basic

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
        print(query.format(ydata))

if __name__ == "__main__":
    main(*sys.argv[1:])

