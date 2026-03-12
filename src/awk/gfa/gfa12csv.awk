# use `-f parse_pansn_str.awk` precede this script

BEGIN {
    FS = OFS = "\t"
    genome_count = 0
    pathcount = 0
}

# extract node id and length
/^S/ {
    if (match($0, /LN:i:[0-9]+/)) {
        s = substr($0, RSTART, RLENGTH)
        split(s, a, ":")
        len = a[3]
    } else {
        len = -1
    }   # in GFA 1 there is a situation that lacks segment length, -1 is set here and pass to subsequent processing
    larr[$2] = len
}

# extract edge
/^L/ {
    print $2, $4 >> edgefp
}

/^P/ {
    split($3, a, ",")

    path_name = $2
    if (!(path_name in paths)) {
        paths[path_name]
        pathcount++
        path_list[pathcount] = path_name
    }

    # Extract genome info from P-line path name
    # Output format for genomes: "sample:haplotype_id:hap_origin"
    resolved = parse_pansn_str($2, pa)
    if (resolved) {
        # PanSN format "sample#haplotype#sequence"
        # pa[1]=sample, pa[2]=haplotype_id, pa[3]=sequence
        sample = pa[1]
        haplotype_id = pa[2]
        hap_origin = "parsed"  # haplotype info parsed from PanSN
    } else if (index($2, "#")) {
        split($2, parts, "#")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"  # haplotype defaulted to 0
    } else if (index($2, ".")) {
        split($2, parts, ".")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"  # haplotype defaulted to 0
    } else {
        # Non-PanSN: use whole path name as sample, default haplotype=0
        sample = $2
        haplotype_id = "0"
        hap_origin = "assumed"  # haplotype defaulted to 0
    }

    # Genome key: "sample:haplotype_id:hap_origin"
    genome_key = sample ":" haplotype_id ":" hap_origin

    if (!(genome_key in genome_keys)) {
        genome_keys[genome_key]
        genome_count++
    }

    # Add path to segment paths (deduplicate per segment/path)
    for (i in a) {
        sid = substr(a[i], 1, length(a[i]) - 1)
        key = sid SUBSEP path_name
        if (!(key in seg_path_seen)) {
            seg_path_seen[key] = 1
            if (sid in seg_paths) {
                seg_paths[sid] = seg_paths[sid] "," path_name
            } else {
                seg_paths[sid] = path_name
            }
        }
    }

    # add tip node
    if (!(tips)) {
        print "head", "0" >> nodefp
        print "tail", "0" >> nodefp
        tips = 1
    }

    # link tip nodes
    nc = length(a)
    start = substr(a[1], 1, length(a[1]) - 1)
    end = substr(a[nc], 1, length(a[nc]) - 1)
    if (!(start in startarr)) {
        startarr[start]
        print "head", start >> edgefp
    }
    if (!(end in endarr)) {
        endarr[end]
        print end, "tail" >> edgefp
    }
}

/^W/ {
    split($7, a, "[<>]")

    # add tip node
    if (!(tips)) {
        print "head", "0" >> nodefp
        print "tail", "0" >> nodefp
        tips = 1
    }

    # link tip nodes
    nc = length(a)
    start = a[2]
    end = a[nc]
    if (!(start in startarr)) {
        startarr[start]
        print "head", start >> edgefp
    }
    if (!(end in endarr)) {
        endarr[end]
        print end, "tail" >> edgefp
    }

    # Extract genome info from W-line
    # W-line format: W <sample> <haplotype_id> <seq_name> ...
    # Genome key format: "sample:haplotype_id:hap_origin"
    sample = $2
    haplotype_id = $3
    hap_origin = "provided"
    genome_key = sample ":" haplotype_id ":" hap_origin
    path_name = sample "#" haplotype_id "#" $4
    if (!(path_name in paths)) {
        paths[path_name]
        pathcount++
        path_list[pathcount] = path_name
    }

    for (i = 2; i in a; i++) {
        key = a[i] SUBSEP path_name
        if (!(key in seg_path_seen)) {
            seg_path_seen[key] = 1
            if (a[i] in seg_paths) {
                seg_paths[a[i]] = seg_paths[a[i]] "," path_name
            } else {
                seg_paths[a[i]] = path_name
            }
        }
    }
    if (!(genome_key in genome_keys)) {
        genome_keys[genome_key]
        genome_count++
    }
}

# print nodes and info
END {
    for (id in larr) {
        if (seg_paths[id] == "") {
            c = 0
        } else {
            c = gsub(",", ",", seg_paths[id]) + 1
        }
        if (pathcount > 0) {
            freq = c / pathcount
        } else {
            freq = 0
        }
        print id, larr[id], freq, seg_paths[id] >> nodefp
    }

    for (genome_key in genome_keys) {
        if (genome_str == "") {
            genome_str = genome_key
        } else {
            genome_str = genome_str "," genome_key
        }
    }
    print "genomes", genome_str >> infofp

    for (i = 1; i <= pathcount; i++) {
        if (path_str == "") {
            path_str = path_list[i]
        } else {
            path_str = path_str "," path_list[i]
        }
    }
    print "paths", path_str >> infofp
    print "paths_total", pathcount >> infofp
}
