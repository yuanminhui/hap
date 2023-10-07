import os
import subprocess


def gzip_gfa(filepath: str):
    """Gzip a GFA file and return the compressed file path."""

    outfp = filepath + ".gz"
    with open(outfp, "w") as file:
        subprocess.run(["gzip", "-c", filepath], stdout=file)

    return outfp


def get_gfa_version(filepath: str) -> float:
    """Get the version of a (gzipped) GFA file. When no `VN` tag in `H` line is
    provided, an examination will run."""

    # a quick scan on version record
    cmd_rv = [
        "zcat",
        filepath,
        "|",
        "head",
        "-n",
        "1",
        "|",
        "awk",
        """'$1 == "H" {for (i = 2; i <= NF; ++i) if ($i ~ /^VN:/) {split($i, a, ":"); print a[3]}}'""",
    ]
    ver = subprocess.check_output(" ".join(cmd_rv), shell=True, text=True)
    try:
        ver = float(ver)
    except ValueError:
        # examine the essential charistics a version has
        cmd_ec = [
            "LC_ALL=C",
            "zcat",
            filepath,
            "|",
            "grep",
            "-m",
            "1",
            "-o",
            "-E",
            "^(E|J|W)",
        ]
        char = subprocess.check_output(" ".join(cmd_ec), shell=True, text=True)
        if char == "E":
            ver = 2.0
        elif char == "J":
            ver = 1.2
        elif char == "W":
            ver = 1.1
        else:
            ver = 1.0
    finally:
        return ver


def move_sequence(filepath: str, gfa_version: float, seqfp: str = None):
    """Move the sequences in a (gzipped) GFA file to `seqfp`, leaving
    a `*` as placeholder, add `LN` tag if not exist, and return the file path of
    the modified GFA file."""

    outfp_base = filepath.replace(".gfa.gz", "")
    if not seqfp:
        seqfp = outfp_base + ".seq.gz"
    outfp = outfp_base + ".min.gfa.gz"
    if os.path.exists(seqfp):
        os.remove(seqfp)

    zcat = [
        "zcat",
        filepath,
    ]
    # `awk` -- move sequences and calculate segment length
    awk = ["|", "awk"]
    gzip = [
        "|",
        "gzip",
    ]
    if gfa_version < 2:
        awk.append(
            f"""'BEGIN {{OFS="\\t"}} /^S/ {{if ($3 != "*") {{cmd = "gzip >> {seqfp}"; print $2, $3 | cmd; close(cmd); len = length($3); $3 = "*"; if (!match($0, /LN:/)) $0 = $0 "\tLN:i:" len}}}} {{print}}'"""
        )
    else:  # GFA 2
        awk.append(
            f"""'BEGIN {{OFS="\\t"}} /^S/ {{if ($4 != "*") {{cmd = "gzip >> {seqfp}"; print $2, $4 | cmd; close(cmd); $4 = "*"}}}} {{print}}'"""
        )

    cmd = zcat + awk + gzip
    with open(outfp, "w") as file:
        subprocess.run(" ".join(cmd), shell=True, stdout=file)

    return outfp


def extract_subgraph_names(
    filepath: str, gfa_version: float, chr_only: bool = True
) -> list[str]:
    """Extract the names of subgraphs from a (gzipped) GFA file. Segment names
    in `W` lines are treated as subgraph names. When no `W` line exists, `PanSN`
    naming convention is required for extracting segment name from ids in `P` or
    `O|U` lines."""

    locale = ["LC_ALL=C"]
    zcat = [
        "zcat",
        filepath,
    ]
    grep = ["|", "grep"]
    awk = [
        "|",
        "awk",
    ]
    # `grep1` -- get records containing subgraph names
    # `awk` -- extract subgraph names
    if gfa_version < 1.1:
        grep1 = grep + ["^P"]
        awk.append(
            r"""'{if (sep=="") {split(" 0,0\\.0;0:0/0\\|0#0_0\\-", seps, "0"); for (i in seps) {sep = seps[i]; c = gsub(sep,sep,$2); if (c==2) break} if (c!=2) exit} {split($2,a,sep); if (length(a)<3) next; else print a[3]}}'"""
        )
    elif gfa_version >= 2.0:
        grep1 = grep + ["-E", "^(O|U)"]
        awk.append(
            r"""'{if (sep=="") {split(" 0,0\\.0;0:0/0\\|0#0_0\\-", seps, "0"); for (i in seps) {sep = seps[i]; c = gsub(sep,sep,$2); if (c==2) break} if (c!=2) exit} {split($2,a,sep); if (length(a)<3) next; else print a[3]}}'"""
        )
    else:
        grep1 = grep + ["^W"]
        awk.append("'{print $4}'")
    sort = ["|", "sort", "-u"]

    cmd = locale + zcat + grep1 + awk + sort
    # filter out non-chromosome level subgraphs
    if chr_only:
        grep2 = grep + ["-i", "^chr"]
        cmd += grep2

    return subprocess.check_output(" ".join(cmd), shell=True, text=True).splitlines()


def extract_subgraph(name: str, gfa_path: str, gfa_version: float, outdir: str):
    """Extract a subgraph by name from a (gzipped) GFA file, returning the sub-GFA's file path."""

    outfp = outdir + "/" + name + ".gfa.gz"

    locale = ["LC_ALL=C"]
    zgrep = ["zgrep", "-E"]
    awk = ["|", "awk"]
    # `zgrep1` -- get records that contain set of nodes from the whole graph by subgraph name
    # `awk` -- extract node ids from set records
    if gfa_version < 2:
        if gfa_version == 1.0:
            zgrep1 = zgrep + [f"^P.*{name}"]
            awk.append(
                """'/^P/ {split($3,a,","); for (i in a) print substr(a[i], 1, length(a[i]) - 1)}'"""
            )
        elif gfa_version == 1.1:
            zgrep1 = zgrep + [f"^W.*{name}"]
            awk.append(
                """'/^W/ {split($7,a,"[<>]"); for (i=2;i in a;i++) print a[i]}'"""
            )
    else:  # GFA 2
        zgrep1 = zgrep + [f"^(O|U).*{name}"]
        awk.append(
            """'/^O/ {split($3,a," "); for (i in a) print a[i]} /^U/ {split($3,a," "); for (i in a) print substr(a[i], 1, length(a[i]) - 1)}'"""
        )
    zgrep1.append(gfa_path)
    # `tee` -- save set records to subgraph
    tee = ["|", "tee", f">(gzip > {outfp})"]
    # `sed` & `zgrep2` -- get related records from the whole graph by segment id
    sed = ["|", "sed", r"'s/^/\t/;s/$/[+-]?\t/'", "|"]
    zgrep2 = zgrep + ["-f", "-", gfa_path]
    gzip = ["|", "gzip", ">>", outfp]

    cmd = locale + zgrep1 + tee + awk + sed + zgrep2 + gzip
    subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash")

    return outfp


def preprocess_gfa(filepath: str, outdir: str):
    """Preprocess a GFA file for subsequent building."""

    gfafp = os.path.normpath(filepath)
    if not os.path.exists(gfafp):
        raise FileNotFoundError(f"File {filepath} not found.")
    outdir = os.path.normpath(outdir)
    if not os.path.exists(outdir):
        os.mkdir(outdir)

    gfagz = (
        gfafp if gfafp.endswith(".gz") else gzip_gfa(gfafp)
    )  # temp gzipped GFA for process performance
    seqfp = outdir + "/" + os.path.basename(gfagz).replace(".gfa.", ".seq.")

    gfaver = get_gfa_version(gfagz)
    gfamin = move_sequence(gfagz, gfaver, seqfp)

    if not gfafp.endswith(".gz"):
        os.remove(gfagz)

    return gfaver, gfamin, seqfp
