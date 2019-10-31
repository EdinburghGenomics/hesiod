# Hesiod

The ancient Greek author Hesiod wrote about the myth of Prometheus.

This Hesiod writes reports about your Promethion (or NanoPore in general) data.

## Features

* Fetches data from the instrument or a network drive
* Imposes a logical naming scheme
* Makes a report, including contamination screen
* Strips out spike-in controls (eg. lambda)
* Concatenates .fastq files to a single .fastq.gz
* Zips down .fast5 files
* Checksums everything
* Logs progress (by sending messages to Request Tracker, if available)
* Tags processed runs for removal from work drive

## Cluster compatibility

Operation is highly parallel. Multiple cells will be processed at once as
they complete on the device.

The processing is initiated via Snakemake, which works on pretty much any
cluster. We use SLURM and SGE.

## Documentation

We're working on it. For now, [ask Tim!](mailto:tim.booth@ed.ac.uk)
