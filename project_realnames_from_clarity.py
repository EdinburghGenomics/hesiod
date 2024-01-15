#!/usr/bin/env python3

"""EdGe business logic - the LIMS is used to look up project numbers and
   see the full name.
   Given a list of short project names, get the real names from the
   LIMS and print the result.
"""

import os, sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from hesiod import dump_yaml

# Project links can be set by an environment var, presumably in environ.sh
# Note that we also respect GENOLOGICSRC and PROJECT_NAME_LIST
PROJECT_PAGE_URL = os.environ.get('PROJECT_PAGE_URL', "http://foo.example.com/")
try:
    if PROJECT_PAGE_URL.format('test') == PROJECT_PAGE_URL:
        PROJECT_PAGE_URL += '{}'
except Exception:
    print("The environment variable PROJECT_PAGE_URL={} is not a valid format string.".format(
                PROJECT_PAGE_URL), file=sys.stderr)
    raise

# A rather contorted way to get project names. If a name list is supplied then
# we bypass connection to tClarity entirely.
def project_real_name(proj_id_list, name_list=''):
    """Resolves a list of project IDs to a name and URL
    """
    res = dict()
    if name_list:
        name_list_split = name_list.split(',')
        # Resolve without going to the LIMS. Note that if you want to disable
        # LIMS look-up without supplying an actuall list of names you can just
        # say "--project_names dummy" or some such thing.
        for p in proj_id_list:
            name_match = [ n for n in name_list_split if n.startswith(p) ]
            if len(name_match) == 1:
                res[p] = dict( name = name_match[0],
                               url  = PROJECT_PAGE_URL.format(name_match[0]) )
            elif p.startswith("Control"):
                res[p] = dict( name = p )
            else:
                res[p] = dict( name = p + "_UNKNOWN" )
    else:
        # Go to the LIMS. The current query mode hits the database as configured
        # by ~/.genologicsrc.
        from hesiod.LIMSQuery import get_project_names

        for p, n in zip(proj_id_list, get_project_names(*proj_id_list)):
            if n:
                res[p] = dict( name = n,
                               url = PROJECT_PAGE_URL.format(n) )
            elif p.startswith("Control"):
                res[p] = dict( name = p )
            else:
                res[p] = dict( name = p + "_UNKNOWN" )

    return res

def main(args):

    if args.take5:
        projects = set([ s[:5] for s in args.projects ])
    else:
        projects = args.projects

    res = project_real_name(projects, os.environ.get('PROJECT_NAME_LIST') )

    # Assuming no exception occurred...
    print(dump_yaml(res, args.out), end='')


def parse_args(*args):
    description = """Looks up project names in the Clarity LIMS
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("projects", nargs='+',
                            help="Supply a list of projects to look up.")
    argparser.add_argument("-o", "--out",
                            help="Where to save the report. If there is an error nothing will be written. Report is always printed.")
    argparser.add_argument("-t", "--take5", action="store_true",
                            help="Just use the first five chars of the project names given. Allows me to pass a list of library/cell names.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
