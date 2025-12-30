# extract_paths_by_name.awk
# Extract path lines (P/O/W/U) that EXACTLY match the given subgraph_name
# Output: Matching path lines only
# Usage: awk -v subgraph_name="chr1" -f parse_pansn_str.awk -f extract_paths_by_name.awk input.gfa
#
# Purpose: Fix chr1/chr10 confusion by using exact field comparison instead of substring matching

BEGIN {
    FS = OFS = "\t"
    if (subgraph_name == "") {
        print "Error: subgraph_name variable not set" > "/dev/stderr"
        print "Usage: awk -v subgraph_name=\"chr1\" -f parse_pansn_str.awk -f extract_paths_by_name.awk input.gfa" > "/dev/stderr"
        exit 1
    }
}

# P lines (GFA 1.0): P <path_name> <segment_names> <overlaps>
/^P/ {
    path_name = $2

    # Try PanSN parsing first (most accurate)
    if (parse_pansn_str(path_name, pa)) {
        # PanSN format: sample#hap#chr or sample.hap.chr
        # pa[1]=sample, pa[2]=haplotype, pa[3]=chromosome
        chr_name = pa[3]
    } else {
        # Fallback: simple delimiter split
        # Try "#" first (most common)
        if (index(path_name, "#")) {
            split(path_name, parts, "#")
            chr_name = parts[length(parts)]  # Last component is chromosome
        } else if (index(path_name, ".")) {
            split(path_name, parts, ".")
            chr_name = parts[length(parts)]
        } else {
            # No delimiter, path_name is the chromosome name
            chr_name = path_name
        }
    }

    # EXACT match (not substring!)
    if (chr_name == subgraph_name) {
        print $0
    }
}

# O lines (GFA 2.0): O <path_name> <segment_references>
/^O/ {
    path_name = $2

    # Same logic as P lines
    if (parse_pansn_str(path_name, pa)) {
        chr_name = pa[3]
    } else {
        if (index(path_name, "#")) {
            split(path_name, parts, "#")
            chr_name = parts[length(parts)]
        } else if (index(path_name, ".")) {
            split(path_name, parts, ".")
            chr_name = parts[length(parts)]
        } else {
            chr_name = path_name
        }
    }

    if (chr_name == subgraph_name) {
        print $0
    }
}

# W lines (GFA 1.1/1.2): W <sample> <hap_index> <seq_name> <start> <end> <walk>
/^W/ {
    seq_name = $4

    # W line seq_name IS the chromosome name directly
    # No need for parsing, just exact comparison
    if (seq_name == subgraph_name) {
        print $0
    }
}

# U lines (GFA 2.0): U <set_name> <id_list>
/^U/ {
    set_name = $2

    # Extract chromosome from set_name (similar to P/O logic)
    if (parse_pansn_str(set_name, pa)) {
        chr_name = pa[3]
    } else {
        if (index(set_name, "#")) {
            split(set_name, parts, "#")
            chr_name = parts[length(parts)]
        } else if (index(set_name, ".")) {
            split(set_name, parts, ".")
            chr_name = parts[length(parts)]
        } else {
            chr_name = set_name
        }
    }

    if (chr_name == subgraph_name) {
        print $0
    }
}
