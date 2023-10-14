
# Hierarchical Pangenome toolkit

A toolkit for data convertion and manipulation in Hierarchical Pangenome model.



[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
![Project Status](https://img.shields.io/badge/status-in--development-orange)


## Status (Important!!)

This program is under active development and not recommended for use or fork.
## Installation

Install from pip

```bash
  pip install hap
```
    
## Usage/Examples

Build a hierarchical pangenome from a GFA file:

```bash
hap build hprc.gfa[.gz]
```

or from subgraphs:

```bash
hap build hprc-subgraphs/
```


Divide a GFA build from a whole genome to chromosome or contig level:

```bash
hap divide hprc.gfa[.gz]
```

Submit the built hierarchical pangenome to database:

```bash
hap submit hprc-subgraphs/ <db://username@hostip:postgreport/dbname>
```

## Support

For any problems, open an issue at the [issue](https://www.github.com/yuanminhui/hap/issues) section.


## Authors

- [@yuanminhui](https://www.github.com/yuanminhui)


## License

The project is under [MIT](https://choosealicense.com/licenses/mit/) license.
