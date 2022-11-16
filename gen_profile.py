#!/usr/bin/env python3

"""Generates a Snakemake profile based on the template in $TOOLBOX/profile_config.yaml

   Missing values will be filled in and the group size can be set as desired.
"""
import os
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from hesiod import load_yaml, dump_yaml
from pprint import pprint
from collections import OrderedDict
import logging as L

# If TOOLBOX is not set, use a default. This script should produce some reasonable output
# even if no env vars are set.
env_copy = {k: v for k, v in os.environ.items() if k}
env_copy.setdefault('TOOLBOX', os.path.abspath(f"{os.path.dirname(__file__)}/toolbox"))

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    # First see if we can output to the right place
    if not args.print:
        try:
            os.mkdir(args.output)
        except FileExistsError:
            if args.clobber:
                L.info(f"Overwriting profile in {args.output}")
                pass
            else:
                raise

    # Now generate the profile
    template_profile = load_yaml(args.template)
    assert isinstance(template_profile, dict)
    final_profile = gen_profile(template_profile, env = env_copy,
                                                  groupsize = args.groupsize,
                                                  jobs = args.jobs)

    # Now save it
    if args.print:
        print(dump_yaml(final_profile), end='')
    else:
        dump_yaml(final_profile, f"{args.output}/config.yaml")

def gen_profile(template, env, groupsize=None, jobs=None):
    """Modify the data structure by filling in various bits of stuff.
    """
    res = OrderedDict()

    # Get the defaults and override them with env vars. Note that env vars set to ''
    # are regarded as unset and ignored when env is copied above.
    settings = template.get("DEFAULTS", {})
    settings.update(env)

    for k, v in template.items():
        # Copy the template items to the res dict
        if k == "DEFAULTS":
            continue
        if k == "group-components" and groupsize:
            L.debug(f"overriding {len(v)} group-components")
            # v should be a list of strings we need to modify
            res[k] = [ f"{x.split('=')[0]}={groupsize}" for x in v ]
            continue
        if k == "jobs" and jobs:
            L.debug(f"overriding jobs")
            res[k] = jobs
            continue

        # Generic fixes-ups
        if isinstance(v, str):
            # Do template substitution
            res[k] = v.format(**settings)
        else:
            # For everything else, just copy
            res[k] = v

    return res

def parse_args(*args):
    description = """Emits a profile for use by Snakemake, based upon the template
                     in the TOOLBOX.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("-o", "--output", default="./profile",
                            help="Directory to create with the profile")
    argparser.add_argument("-t", "--template", default=f"{env_copy['TOOLBOX']}/profile_config.yaml",
                            help="YAML file to use as a profile template.")
    argparser.add_argument("-g", "--groupsize", type=int,
                            help="Size of group components for batching small jobs.")
    argparser.add_argument("-j", "--jobs", type=int,
                            default=(int(env_copy['SNAKE_THREADS']) if env_copy.get('SNAKE_THREADS') else None),
                            help="Max concurrent jobs to be run (--jobs setting in Snakemake).")
    argparser.add_argument("-p", "--print", action="store_true",
                            help="Just print the profile/config.yaml don't save it out.")
    argparser.add_argument("--clobber", action="store_true",
                            help="Delete the output directory if it already exists.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())

