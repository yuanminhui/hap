# use `-f parse_pansn_str.awk` precede this script

BEGIN {
    FS = OFS = "\t"
    genome_count = 0
    pathcount = 0
}

# extract node id and length
/^S/ {
    larr[$2] = $3
}

# extract edge
/^E/ {
    source = substr($3, 1, length($3) - 1);
    target = substr($4, 1, length($4) - 1);
    print source, target >> edgefp;
}

/^O/ {
    split($3, a, " ")

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

    path_name = $2
    if (!(path_name in paths)) {
        paths[path_name]
        pathcount++
        path_list[pathcount] = path_name
    }

    # Extract genome info from path name
    # Output format for genomes: "sample:haplotype_id:hap_origin"
    resolved = parse_pansn_str($2, pa)
    if (resolved) {
        sample = pa[1]
        haplotype_id = pa[2]
        hap_origin = "parsed"
    } else if (index($2, "#")) {
        split($2, parts, "#")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"
    } else if (index($2, ".")) {
        split($2, parts, ".")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"
    } else {
        sample = $2
        haplotype_id = "0"
        hap_origin = "assumed"
    }
    genome_key = sample ":" haplotype_id ":" hap_origin
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
    if (!(genome_key in genome_keys)) {
        genome_keys[genome_key]
        genome_count++
    }   # non-duplicate haplotype names
}

/^U/ {
    split($3, a, " ")

    # add tip node
    if (!(tips)) {
        print "head", "0" >> nodefp
        print "tail", "0" >> nodefp
        tips = 1
    }

    # link tip nodes
    nc = length(a)
    start = a[1]
    end = a[nc]
    if (!(start in startarr)) {
        startarr[start]
        print "head", start >> edgefp
    }
    if (!(end in endarr)) {
        endarr[end]
        print end, "tail" >> edgefp
    }

    path_name = $2
    if (!(path_name in paths)) {
        paths[path_name]
        pathcount++
        path_list[pathcount] = path_name
    }

    # Extract genome info from path name
    # Output format for genomes: "sample:haplotype_id:hap_origin"
    resolved = parse_pansn_str($2, pa)
    if (resolved) {
        sample = pa[1]
        haplotype_id = pa[2]
        hap_origin = "parsed"
    } else if (index($2, "#")) {
        split($2, parts, "#")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"
    } else if (index($2, ".")) {
        split($2, parts, ".")
        sample = parts[1]
        haplotype_id = "0"
        hap_origin = "assumed"
    } else {
        sample = $2
        haplotype_id = "0"
        hap_origin = "assumed"
    }
    genome_key = sample ":" haplotype_id ":" hap_origin
    for (i in a) {
        sid = a[i]
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
