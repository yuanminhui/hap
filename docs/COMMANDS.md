## hap CLI commands

This file is generated automatically during tests. It enumerates commands discovered from the Click CLI.

Run generator:

```bash
PYTHONPATH=src python -m hap.__main__ --help
```

Commands:

- build: Build-related commands
  - run: Build a Hierarchical Pangenome
- sequence: Sequence management commands
  - add: Bulk import sequences from FASTA/FASTQ into the database
  - get: Get sequences by ID(s) or regex
  - edit: Edit a sequence for a given segment ID
  - delete: Delete sequences by ID(s)
- config: Get and set configurations
  - get: Get a configuration value
  - set: Configuration key to set
  - unset: Configuration key to unset
  - list: List all configurations

Note: For exact options, refer to `hap <command> --help`.

