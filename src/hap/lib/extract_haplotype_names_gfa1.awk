# use `-f parse_pansn_str.awk` precede this script

BEGIN { 
    FS = OFS = "\t"
}

/^P/ {
    resolved = parse_pansn_str($2, pa)
    if (!resolved) {
        next
    }
    n = pa[1] "." pa[2]
    if (!(n in haplos)) {
        haplos[n]
    }
}

/^W/ { 
    n = $2 "." $3
    if (!(n in haplos)) {
        haplos[n]
    }
}

END {
    for (n in haplos) {
        print n
    }
}