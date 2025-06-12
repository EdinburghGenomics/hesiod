#!/usr/bin/env python3

"""EdGe business logic - decide if an experiment is to be processed as one
   of ours (full pipeline) or a visitor project (md5sum only) or other
   experiments are marked as "test" (sync but no processing).

   Given a single experiment name, print the result in YAML format.
"""

import sys, re
from hesiod import dump_yaml

def classify(expt_name):
    # Full experiment names start with the date and instrument - eg.
    # 20220420_EGS1_14211AT0050
    mo = re.fullmatch(r"\d{8}_[A-Z0-9]{3,}_(.*)", expt_name)
    if mo:
        expt_name = mo.group(1)
    else:
        # Looks sus
        return dict(type="unknown")

    # Visitor expts start "v_" but be a little forgiving of the exact format.
    mo_v = re.search(r"^v[_-]+([a-z0-9]+)(?:[_-]|$)", expt_name, flags=re.IGNORECASE)
    # Internal expts start with a number.
    mo_i = re.search(r"^[0-9]", expt_name)

    if mo_v:
        return dict(type = "visitor",
                    uun  = mo_v.group(1).lower())
    elif mo_i:
        return dict(type = "internal")

    # Default if the name is unrecognised
    return dict(type = "test")

if __name__ == "__main__":
    print(dump_yaml(classify(*sys.argv[1:])), end="")
