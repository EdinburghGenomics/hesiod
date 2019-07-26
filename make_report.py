#!/usr/bin/env python3
import os, sys, re
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat
from datetime import datetime
from collections import OrderedDict, namedtuple
import yaml, yamlloader
import shutil
import base64

from hesiod import hesiod_version, glob, parse_cell_name, load_yaml

def format_report(all_info, pipedata, run_status, aborted_list):
    """Makes the report as a list of strings (lines)
    """

    res = []
    P = lambda *a: res.extend(a or [''])

    # Get the run(s)
    runs = sorted(set([ i['Run'] for i in all_info.values() ]))
    instr = sorted(set([ i['Run'].split('_')[1] for i in all_info.values() ]))
    libs = sorted(set([ i['Cell'].split('/')[0] for i in all_info.values() ]))

    # Header
    P( "% Promethion run {}".format(",".join(runs)),
       "% Hesiod version {}".format(pipedata['version']),
       "% {}".format(datetime.now().strftime("%A, %d %b %Y %H:%M")) )

    # Run metadata
    P()
    P( "# About this run (experiment? project?)")
    P()
    P( '<dl class="dl-horizontal">' )
    P( '<dt>RunID</dt> <dd>{}</dd>'.format(",".join(runs)) )
    P( '<dt>Instrument</dt> <dd>{}</dd>'.format(",".join(instr)) )
    P( '<dt>CellCount</dt> <dd>{}</dd>'.format(len(all_info)) )
    P( '<dt>LibraryCount</dt> <dd>{}</dd>'.format(len(libs)) )
    P( '<dt>StartTime</dt> <dd>{}</dd>'.format((pipedata['start_times'] or ['unknown'])[0]) )
    P( '<dt>LastCellTime</dt> <dd>{}</dd>'.format((pipedata['start_times'] or ['unknown'])[-1]) )
    P( '</dl>' )

    for cell, ci in all_info.items():
        P()
        P( "## Cell {}".format(cell) )
        P()
        P( ":::::: {.bs-callout}" )
        P( '<dl class="dl-horizontal">' )

        # Basic cell metadata
        for k, v in ci.items():
            if not k.startswith("_"):
                P('<dt>{}</dt> <dd>{}</dd>'.format(k,escape(v)))
        P( '</dl>' )
        P()

        # Embed some files from MinionQC
        minqc_base = os.path.dirname(ci['_minionqc'])
        for f in ['length_histogram.png', 'length_vs_q.png', 'yield_over_time.png']:
            res.append('\n### {}\n'.format(f))
            res.append("<div class='flex'>")
            res.append(" ".join(
                    "[plot](img/minqc_{ci[Library]}_{ci[CellID]}_{f}){{.thumbnail}}".format(ci=ci, f=f)
                    for _ in [1]
                ))
            res.append("</div>")


        # Link to the NanoPlot report (for now - should embed thumbnails)
        P( "[NanoPlot Report](NanoPlot_{ci[Library]}_{ci[CellID]}-report.html)".format(ci=ci) )

        # Blob plots as per SMRTino (the YAML file is linked rather than embedded but it's the
        # same otherwise)
        if '_blobs' in ci:
            for plot_group in load_yaml(ci['_blobs']):

                res.append('\n### {}\n'.format(plot_group['title']))

                # plot_group['files'] will be a a list of lists, so plot
                # each list a s a row.
                for plot_row in plot_group['files']:
                    res.append("<div class='flex'>")
                    res.append(" ".join(
                            "[plot](img/{f}){{.thumbnail}}".format(f=os.path.basename(p))
                            for p in plot_row
                        ))
                    res.append("</div>")

        P( "::::::" )

    P()
    P("*~~~*")
    return res

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    all_info = dict()
    # Basic basic basic
    for y in args.yamls:
        yaml_info = load_yaml(y)

        # Sort by cell ID - all YAML must have this.
        assert yaml_info.get('Cell'), "All yamls must have a Cell ID"

        all_info[yaml_info['Cell']] = yaml_info

    # Glean some pipeline metadata
    if args.pipeline:
        pipedata = get_pipeline_metadata(args.pipeline)
    else:
        pipedata = dict(version=hesiod_version)

    # And some more of that
    status_info = load_status_info(args.status, fudge=args.fudge_status)

    rep = format_report(all_info,
                        pipedata = pipedata,
                        run_status = status_info,
                        aborted_list = status_info.get('CellsAborted'))

    if (not args.out) or (args.out == '-'):
        print(*rep, sep="\n")
    else:
        L.info("Writing to {}".format(args.out))
        with open(args.out, "w") as ofh:
            print(*rep, sep="\n", file=ofh)

        copy_dest = os.path.dirname(args.out) or '.'
        L.info("Copying files to {}".format(copy_dest))

        copy_files(all_info, copy_dest)

def copy_files(all_info, base_path):
    """ We need to copy the NanoPlot, MinionQC, Blob reports into here.
        Base path will normally be wherever the report is being made.
    """
    os.makedirs(os.path.join(base_path, "img") , exist_ok=True)

    for cell, ci in sorted(all_info.items()):

        if '_blobs' in ci:
            blob_base = os.path.dirname(ci['_blobs'])

            for png in glob(blob_base + '/*.png'):
                dest_png = os.path.basename(png)
                shutil.copy(png, os.path.join(base_path, "img", dest_png))

        if '_nanoplot' in ci:
            nano_base = os.path.dirname(ci['_nanoplot'])

            src_rep = "{nb}/NanoPlot-report.html".format(nb=nano_base)
            dest_rep = "NanoPlot_{ci[Library]}_{ci[CellID]}-report.html".format(ci=ci)
            shutil.copy(src_rep, os.path.join(base_path, dest_rep))

        if '_minionqc' in ci:
            min_base = os.path.dirname(ci['_minionqc'])

            for png in glob(min_base + '/*.png'):
                dest_png = "minqc_{ci[Library]}_{ci[CellID]}_{f}".format(ci=ci, f=os.path.basename(png))
                shutil.copy(png, os.path.join(base_path, "img", dest_png))

def get_pipeline_metadata(pipe_dir):
    """ Read the files in the pipeline directory to find out some stuff about the
        pipeline. This is in addition to what we get from pb_run_status.
    """
    # The start_times file reveals the versions applied
    starts = list()

    try:
        with open(pipe_dir + '/start_times') as fh:
            for l in fh:
                starts.append(l.strip())
    except Exception:
        # Meh.
        pass

    versions = set([ l.split('@')[0] for l in starts ])
    # Plus there's the current version
    versions.add(hesiod_version)

    # Get the name of the directory what pipe_dir is in
    rundir = os.path.basename( os.path.realpath(pipe_dir + '/..') )

    return dict( version = '+'.join(sorted(versions)),
                 start_times = [ l.split('@')[1] for l in starts ],
                 rundir = rundir )

def escape(in_txt, backwhack=re.compile(r'([][\`*_{}()#+-.!])')):
    """ HTML escaping is not the same as markdown escaping
    """
    return re.sub(backwhack, r'\\\1', str(in_txt))

def load_status_info(sfile, fudge=None):
    """ Parse the output of pb_run_status.py, either from a file or more likely
        from a BASH <() construct - we don't care.
        It's quasi-YAML format but I'll not use the YAML parser. Also I want to
        preserve the order.
    """
    res = OrderedDict()
    if sfile:
        with open(sfile) as fh:
            for line in fh:
                k, v = line.split(':', 1)
                res[k.strip()] = v.strip()
    if fudge:
        # Note this keeps the order or else adds the status on the end.
        res['PipelineStatus'] = fudge
    return res

def parse_args(*args):
    description = """ Makes a report (in PanDoc format) for a run (aka an experiment), by compiling the info from the
                      YAML files that are made per-cell.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("yamls", nargs='*',
                            help="Supply a list of info.yml files to compile into a report.")
    argparser.add_argument("--minionqc", default=None,
                           help="Add minionqc combined stats")
    argparser.add_argument("-p", "--pipeline", default="rundir/pipeline",
                            help="Directory to scan for pipeline meta-data.")
    argparser.add_argument("-s", "--status", default=None,
                            help="File containing status info on this run.")
    argparser.add_argument("-f", "--fudge_status", default=None,
                            help="Override the PipelineStatus shown in the report.")
    argparser.add_argument("-o", "--out",
                            help="Where to save the report. Defaults to stdout.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
