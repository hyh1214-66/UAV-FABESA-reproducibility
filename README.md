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
cross_scheme/   Cross-scheme benchmark and a partial data release
                cross_scheme_benchmark.py    Benchmark driver
                cross_scheme_raw_subset.csv  900 of the 3,000 execution records
```

## Availability of Code and Data
This repository provides the core cryptographic implementation of the UAV-FABESA framework and is under continuous maintenance and development. At present, it makes publicly available the following: (i) the base cryptographic implementation; (ii) the cross-scheme benchmark scripts; and (iii) a representative subset of the benchmark records.

Because some of the code is subject to the research group's data-management requirements and ongoing follow-up studies, it is not fully released here. These materials are available from the corresponding author upon reasonable request.

To support research transparency, the associated paper provides a detailed description of the experimental configuration, evaluation procedure, data-processing method, and statistical analysis. If you have questions about specific results reported in the paper, please contact the corresponding author for methodological explanation and technical clarification.

Supplementary materials that can be made public are being added to this repository.

## Notes
All implementations use the BN254 pairing curve with fixed random seeds. Each
configuration is repeated N = 50 times.
