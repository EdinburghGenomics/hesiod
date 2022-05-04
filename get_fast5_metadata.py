#!/usr/bin/env python3

"""Given a directory of .fast5 files, extract some metadata:
    1) Version of the .fast5 files
    2) Start time of the run
    3) Version of Guppy (or other basecaller)
   Inputs:
    A directory where .fast5 files may be found
"""

import os, sys, re
import logging
import gzip
from io import BytesIO
import shutil
import math
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from contextlib import suppress

# For parsing of ISO/RFC format dates (note that newer Python has datetime.datetime.fromisoformat
# but we're using dateutil.parser.isoparse from python-dateutil 2.8)
from dateutil.parser import isoparse

# For reading teh fast5...
import h5py

from hesiod import dump_yaml, glob

def main(args):

    logging.basicConfig( level = logging.DEBUG if args.verbose else logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    if os.path.isdir(args.fast5):
        logging.debug("Scanning .fast5[.gz] files in '{}'".format(args.fast5) )
        md = md_from_fast5_dir(args.fast5)
    else:
        logging.debug("Reading from single file '{}'".format(args.fast5) )
        md = md_from_fast5_file(args.fast5)

    print(dump_yaml(md), end='')

def md_from_fast5_dir(f5_dir):
    """Read from the directory of fast5 files and return a dict of metadata.
    """
    f5_files = glob(os.path.join(f5_dir, '*.fast5'))
    if not f5_files:
        # Try zipped...
        logging.debug("No .fast5 files, maybe .fast5.gz?")
        f5_files = glob(os.path.join(f5_dir, '*.fast5.gz'))

    logging.debug("Found {} files".format(len('f5_files')))
    assert f5_files, "No fast5[.gz] files found."

    # Use the first one
    return md_from_fast5_file(f5_files[0])

def md_from_fast5_file(f5_file):
    """Read from a specified fast5 file and return a dict of metadata
    """
    if f5_file.endswith('.gz'):
        # Unpack the entire file in memory - much faster than a direct read from gzip handle
        with BytesIO() as bfh:
            with gzip.open(f5_file, 'rb') as zfh:
                shutil.copyfileobj(zfh, bfh)
            bfh.seek(0)

            return read_fast5(bfh)
    else:
        # Let h5py open the file directly
        return read_fast5(f5_file)

def read_fast5(fobj):
    """Gets the metadata from a single fast5 file
       I'd assumed I could do this using ont_fast5_api but for various reasons it seems
       far simpler to code it myself. However I have looked at code from
       https://github.com/nanoporetech/ont_fast5_api/blob/master/ont_fast5_api/fast5_info.py
       as a starting point.
    """
    res = OrderedDict()
    for x in ['Fast5Version', 'StartTime', 'GuppyVersion']:
        res[x] = 'unknown'

    with h5py.File(fobj, 'r') as handle:

        # Version check. In development the files are '1.0'
        # so maybe I should check for this?
        res['Fast5Version'] = handle.attrs['file_version']

        # Just as the metadata is the same for each file, it's the same for each
        # read, so just get the first one.
        read0_name, read0 = next(iter((handle.items())))

        # Run ID (should be in the filename anyway!)
        res['RunID'] = read0.attrs['run_id']

        # Stuff from 'context_tags'
        for x in ['ExperimentType', 'SequencingKit', 'BasecallConfig']:
            res[x] = 'unknown'
        # Sometimes keys are missing, I guess.
        with suppress(KeyError):
            res['ExperimentType'] = read0['context_tags'].attrs['experiment_type']
        with suppress(KeyError):
            res['SequencingKit']  = read0['context_tags'].attrs['sequencing_kit']
        with suppress(KeyError):
            res['BasecallConfig']   = read0['context_tags'].attrs['basecall_config_filename']

        # Stuff from 'tracking_id'
        res['StartTime']    = read0['tracking_id'].attrs['exp_start_time']
        try:
            res['GuppyVersion'] = read0['tracking_id'].attrs['guppy_version']
        except KeyError:
            # Some old files have no Guppy version. In which case remove the placeholder
            # entirely.
            del res['GuppyVersion']

        # Now look for basecalling metadata - actually I removed this as it's not in the
        # newer fast5 files and not very useful anyway.

    # Decode all byte strings in res, and re-format dates.
    for k in list(res):
        with suppress(AttributeError):
            res[k] = res[k].decode()

        if k.endswith("Time"):
            res[k] = isoparse(res[k]).strftime('%A, %d %b %Y %H:%M:%S')

    return res

""" Here's what we expect to see in 'context_tags':
(Pdb) pp dict(read0['context_tags'].attrs)
{'basecall_config_filename': b'dna_r9.4.1_450bps_prom.cfg',
 'experiment_duration_set': b'3840',
 'experiment_type': b'genomic_dna',
 'fast5_output_fastq_in_hdf': b'1',
 'fast5_raw': b'1',
 'fast5_reads_per_folder': b'8000',
 'fastq_enabled': b'1',
 'fastq_reads_per_file': b'4000',
 'filename': b'pct0112_20190425_0004a30b00269581_2_a7_d7_sequencing_run_11608ge0009_79552',
 'flowcell_type': b'flo-pro002',
 'kit_classification': b'none',
 'local_basecalling': b'1',
 'sample_frequency': b'4000',
 'sequencing_kit': b'sqk-lsk109',
 'user_filename_input': b'11608ge0009'}
"""

""" Here's what we expect to see regarding the basecalling
(Pdb) pp dict(read0['Analyses']['Basecall_1D_000'].attrs)
{'name': b'MinKNOW-Live-Basecalling',
 'time_stamp': b'2019-04-25T16:25:18Z',
 'version': b'3.1.23'}
"""

""" Here's what we expect to see in the tracking_id part
(Pdb) pp dict(read0['tracking_id'].attrs)
{'asic_id': b'0004A30B00250C3F',
 'asic_id_eeprom': b'0004A30B00250C3F',
 'asic_temp': b'33.691181',
 'asic_version': b'Unknown',
 'auto_update': b'0',
 'auto_update_source': b'https://mirror.oxfordnanoportal.com/software/MinKNOW/',
 'bream_is_standard': b'0',
 'device_id': b'2-E1-H1',
 'device_type': b'promethion',
 'distribution_status': b'stable',
 'distribution_version': b'19.06.8',
 'exp_script_name': b'629db1f5c6439aa6be9a65613d0f255b66f59bf3',
 'exp_script_purpose': b'sequencing_run',
 'exp_start_time': b'2019-07-05T15:33:25Z',
 'flow_cell_id': b'PAD49515',
 'guppy_version': b'3.0.4+e7dbc23',
 'heatsink_temp': b'36.932358',
 'hostname': b'PCT0112',
 'hublett_board_id': b'01377e66769b58da',
 'hublett_firmware_version': b'2.0.12',
 'installation_type': b'nc',
 'ip_address': b'',
 'local_firmware_file': b'1',
 'mac_address': b'',
 'operating_system': b'ubuntu 16.04',
 'protocol_group_id': b'20190705_11800AA0001',
 'protocol_run_id': b'4ead8234-7d9b-43ec-99b4-6931aad36237',
 'protocols_version': b'4.1.8',
 'run_id': b'c44e8c0e965e6f9874255389cafda392630dd64e',
 'sample_id': b'11800AA0001L01_25kb_shear',
 'satellite_board_id': b'0000000000000000',
 'satellite_firmware_version': b'2.0.12',
 'usb_config': b'firm_1.2.3_ware#rbt_4.5.6_rbt#ctrl#USB3',
 'version': b'3.4.5'}
"""

def parse_args(*args):
    description = """Extract various bits of metadata from the first read in a .fast5 file."""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("fast5", default='.', nargs='?',
                        help="Directory to scan for .fast5[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

