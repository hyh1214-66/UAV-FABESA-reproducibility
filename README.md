# FABESA Reproducibility Package 

This repository provides the base cryptographic implementation that underpins
the UAV-FABESA framework, together with a partial release of the cross-scheme
benchmark resources. It is under continuous maintenance and improvement.

## Environment
- Ubuntu 20.04 x86-64
- Python 3.9+ (tested with 3.9.18 via pyenv)
- [Charm-Crypto 0.50](https://github.com/JHUISI/charm) (compile from source: `./configure.sh && make install && pip install -e .`)
- NumPy, matplotlib, PyYAML

## Contents
```
ABE/            Baseline CP-ABE implementations
                bswcp (BSW, CCS 2007), waterscp (Waters, PKC 2011),
                FAME_CP (CCS 2017), FABEO_CP (CCS 2022), FABESA_CP (CCS 2024)
msp/            Monotone span program
policytree.py   Policy string parser
secretutil.py   Secret-sharing utilities
config.py       Configuration loader
config.yaml     Default configuration
cross_scheme/   Cross-scheme benchmark scripts and a partial data release
                cross_scheme_benchmark.py    Benchmark driver
                cross_scheme_figure.py       Figure-generation script
                cross_scheme_raw_subset.csv  900 of the 3,000 execution records
```

## Availability of Code and Data
This repository is under continuous maintenance and improvement. At present it
makes publicly available (i) the base cryptographic implementation, (ii) the
cross-scheme benchmark scripts, and (iii) a representative subset of the
benchmark records: 900 of the 3,000 runs, corresponding to cold-start mode at
policy sizes 5, 20, and 50 for all six schemes.

The complete set of 3,000 cross-scheme benchmark execution records, the raw
simulation outputs, and the processed experimental data are not included in
this repository. Because these materials are subject to the research group's
data-management requirements and to ongoing follow-up studies, they are not
released here as a complete public dataset. They are available from the
corresponding author upon reasonable request.

To support transparency, the manuscript details the experimental configuration,
testing procedure, data-processing method, and statistical analysis. Any
additional materials that can be made public will be added to this repository
incrementally as the project progresses.

## Notes
All implementations use the BN254 pairing curve with fixed random seeds. Each
configuration is repeated N = 50 times.
