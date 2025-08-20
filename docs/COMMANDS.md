## hap CLI commands

Generated from Click introspection.

- build: Build-related commands.
  - run: 
Build a Hierarchical Pangenome from a pangenome graph in GFA format, and
save to database.

PATH: Path to the pangenome graph in GFA format. If `-s/--from-subgraphs`
is specified, PATH should be a list of subgraphs or a directory containing
the subgraphs.
- config: Configuration management commands.
  - get:
  - list:
  - set:
  - unset:
- sequence: Manage segment sequences in the database.
  - add: Bulk import sequences from FASTA/FASTQ into the database.
  - delete: Delete sequences by ID(s).
  - edit: Edit a sequence for a given segment ID.
  - get: Get sequences by ID(s) or regex.
