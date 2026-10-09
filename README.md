# FABESA Reproducibility Package 

This repository provides the base cryptographic implementation that underpins
the UAV-FABESA framework.

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
```

## Availability
The complete experiment scripts, the 3,000 cross-scheme benchmark execution
records, the raw simulation outputs, and the processed experimental data are
not included in this repository. They are available from the corresponding
author upon reasonable request.

## Notes
All implementations use the BN254 pairing curve with fixed random seeds.
