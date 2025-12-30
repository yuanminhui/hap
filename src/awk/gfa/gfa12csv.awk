# use `-f parse_pansn_str.awk` precede this script

BEGIN {
    FS = OFS = "\t"
    hapcount = 0
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

    # Extract genome info from P-line path name
    # Output format for sources: "sample:haplotype_index:haplotype_origin"
    resolved = parse_pansn_str($2, pa)
    if (resolved) {
        # PanSN format "sample#haplotype#sequence"
        # pa[1]=sample, pa[2]=haplotype_index, pa[3]=sequence
        sample = pa[1]
        haplotype = pa[2]
        origin = "parsed"  # haplotype info parsed from PanSN
    } else {
        # Non-PanSN: use whole path name as sample, default haplotype=0
        sample = $2
        haplotype = "0"
        origin = "assumed"  # haplotype defaulted to 0
    }

    # Genome key: "sample:haplotype_index:haplotype_origin"
    n = sample ":" haplotype ":" origin

    if (!(n in haplos)) {
        haplos[n]
        hapcount++
    }

    # Add genome to segment sources
    for (i in a) {
        sid = substr(a[i], 1, length(a[i]) - 1)
        if (sid in harr) {
            harr[sid] = harr[sid] "," n
        } else {
            harr[sid] = n
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
    # W-line format: W <sample> <haplotype_index> <seq_name> ...
    # Genome key format: "sample:haplotype_index:haplotype_origin"
    sample = $2
    haplotype = $3
    origin = "provided"
    n = sample ":" haplotype ":" origin

    for (i = 2; i in a; i++) {
        if (a[i] in harr) {
            harr[a[i]] = harr[a[i]] "," n
        } else {
            harr[a[i]] = n
        }
    }
    if (!(n in haplos)) {
        haplos[n]
        hapcount++
    }
}

# print nodes and info
END {
    for (id in larr) {
        c = gsub(",", ",", harr[id]) + 1
        print id, larr[id], c / hapcount, harr[id] >> nodefp
    }

    for (hap in haplos) {
        if (hapstr == "") {
            hapstr = hap
        } else {
            hapstr = hapstr "," hap
        }
    }
    print "haplotypes", hapstr >> infofp
}
