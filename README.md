# Hesiod

The ancient Greek author Hesiod wrote about the myth of Prometheus.

This Hesiod writes reports about your Promethion (or other NanoPore) data.

## Features

* Fetches data from the instrument or a network drive
* Imposes a logical naming scheme
* Concatenates .fastq files to a single .fastq.gz
* Checksums everything
* Runs NanoPlot
* Extracts useful metadata from POD5 files
* Makes a report, including contamination screen
* Logs progress (by sending messages to Request Tracker, if available)
* Tags processed runs for removal from work drive
* State-machine-driven operation
* Works with barcoded and non-barcoded runs

as of version 3 it does not:

* ~~Strip out spike-in controls (eg. lambda)~~ *(this feature may come back)*
* ~~Zips down .fast5/.pod5 files~~ *(they are no longer worth compressing)*

## Cluster compatibility

Operation is highly parallel. Multiple cells will be processed at once as
they complete on the device. This even works with multiple devices.

The processing is initiated via Snakemake, which works on pretty much any
cluster so long as you have a shared file system. We use SLURM and SGE.

## Documentation

We're working on it. For now, [ask Tim!](mailto:tim.booth@ed.ac.uk)
