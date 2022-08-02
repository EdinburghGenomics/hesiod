# Hesiod

The ancient Greek author Hesiod wrote about the myth of Prometheus.

This Hesiod writes reports about your Promethion (or other NanoPore) data.

## Features

* Fetches data from the instrument or a network drive
* Imposes a logical naming scheme
* Strips out spike-in controls (eg. lambda)
* Concatenates .fastq files to a single .fastq.gz
* ~~Zips down .fast5 files~~ *(they are no longer worth compressing)*
* Checksums everything
* Runs NanoPlot
* Extracts useful metadata from FAST5 files
* Makes a report, including contamination screen
* Logs progress (by sending messages to Request Tracker, if available)
* Tags processed runs for removal from work drive
* State-machine-driven operation
* Works with barcoded and non-barcoded runs

## Cluster compatibility

Operation is highly parallel. Multiple cells will be processed at once as
they complete on the device. This even works with multiple devices.

The processing is initiated via Snakemake, which works on pretty much any
cluster so long as you have a shared file system. We use SLURM and SGE.

## Documentation

We're working on it. For now, [ask Tim!](mailto:tim.booth@ed.ac.uk)
