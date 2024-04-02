# Parse a PanSN string, resolve its delimiter, save the split array to `parr` and return 1 if successfully resolved.
# If no vaild delimeter is found, `delim` is set empty and return 0.
# If current string can't be split by resolved delimeter, `parr` is set empty and return 0.
function parse_pansn_str(pansnstr, parr) {

delete parr

# get PanSN delimiter for the whole file
if (delim == "") {
    split(" 0,0\\.0;0:0/0\\|0#0_0\\-", pps_delims, "0")   # possible delimiters

    # find delimiter that occurs exactly twice
    for (i in pps_delims) {
        delim = pps_delims[i]
        pps_c = gsub(delim, delim, pansnstr)
        if (pps_c == 2) {
            break
        }
    }

    # doesn't follow PanSN convention, can't extract subgraph name
    if (pps_c != 2) {
        delim = ""
        return 0
    }
}

split(pansnstr, parr, delim)
if (length(parr) != 3) {
    delete parr
    return 0
} else {
    return 1
}
}
