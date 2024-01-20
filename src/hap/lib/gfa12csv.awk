# use `-f parse_pansn_str.awk` precede this script

BEGIN { 
    OFS = "\t"
    hapcount = 0

    # add tip node
    print "start", "0" > nodefp
    print "end", "0" > nodefp
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

    # link tip nodes
    nc = length(a)
    print "start", substr(a[1], 1, length(a[1]) - 1) >> edgefp
    print substr(a[nc], 1, length(a[nc]) - 1), "end" >> edgefp

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
    if (!(n in haps)) {
        haps[n]
        hapcount++
    }   # non-duplicate haplotype names
}

/^W/ { 
    split($7, a, "[<>]")

    # link tip nodes
    nc = length(a)
    print "start", a[2] >> edgefp
    print a[nc], "end" >> edgefp

    # extract haplotype name
    n = $2 "." $3
    for (i = 2; i in a; i++) {
        if (a[i] in harr) {
            harr[a[i]] = harr[a[i]] "," n
        } else {
            harr[a[i]] = n
        }
    }
    if (!(n in haps)) {
        haps[n]
        hapcount++
    }
}

# print nodes and info
END { 
    for (id in larr) {
        c = gsub(",", ",", harr[id]) + 1
        print id, larr[id], c / hapcount, harr[id] >> nodefp
    }
    
    for (hap in haps) {
        if (hapstr == "") {
            hapstr = hap
        } else {
            hapstr = hapstr "," hap
        }
    }
    print "haplotypes", hapstr >> infofp
}
