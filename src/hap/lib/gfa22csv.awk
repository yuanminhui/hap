# use `-f parse_pansn_str.awk` precede this script

BEGIN {
    FS = OFS = "\t"
    hapcount = 0
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

    # extract haplotype name
    resolved = parse_pansn_str($2, pa)
    if (!resolved) {
        next
    }
    n = pa[1] "." pa[2]
    for (i in a) {
        sid = substr(a[i], 1, length(a[i]) - 1)
        if (sid in harr) {
            harr[sid] = harr[sid] "," n
        } else {
            harr[sid] = n
        }   # NOTE: simply add on, may contain duplicates
    }
    if (!(n in haplos)) {
        haplos[n]
        hapcount++
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

    # extract haplotype name
    resolved = parse_pansn_str($2, pa)
    if (!resolved) {
        next
    }
    n = pa[1] "." pa[2]
    for (i in a) {
        sid = a[i]
        if (sid in harr) {
            harr[sid] = harr[sid] "," n
        } else {
            harr[sid] = n
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
