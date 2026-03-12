# use `-f parse_pansn_str.awk` precede this script

BEGIN { 
    FS = OFS = "\t"
}

/^P/ {
    resolved = parse_pansn_str($2, pa)
    if (resolved) {
        sample = pa[1]
        haplotype = pa[2]
    } else if (index($2, "#")) {
        split($2, parts, "#")
        sample = parts[1]
        haplotype = "0"
    } else if (index($2, ".")) {
        split($2, parts, ".")
        sample = parts[1]
        haplotype = "0"
    } else {
        sample = $2
        haplotype = "0"
    }
    n = sample "#" haplotype
    if (!(n in haplos)) {
        haplos[n]
    }
}

/^W/ { 
    n = $2 "#" $3
    if (!(n in haplos)) {
        haplos[n]
    }
}

END {
    for (n in haplos) {
        print n
    }
}
