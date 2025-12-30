# parse_gfa_paths.awk
# Extract and validate path information from GFA files (P/O/W lines)
# Output format: path_name\tgenome_name\tnormalized_walk
# Usage: awk -f parse_pansn_str.awk -f parse_gfa_paths.awk file.gfa
#
# Features:
# 1. Scans all path line types (P, O, W) in a single pass
# 2. Validates FORWARD-ONLY orientation (rejects '-' orientation)
# 3. Normalizes walk to space-separated "segmentID segmentID ..." format
# 4. Handles empty path names
# 5. Resolves genome names via PanSN/delimiter conventions
#
# Error reporting to stderr:
# - Invalid orientation errors
# - Empty path name warnings
# - Genome resolution failures (via ERROR: prefix)

BEGIN {
    FS = OFS = "\t"
    error_count = 0
}

# Normalize walk and validate forward-only orientation
# Returns normalized walk string or empty string on error
# P format: "s1+,s2-,s3+" → validates → "s1 s2 s3" or ERROR
function normalize_walk_p(walk_str, path_name,    segments, i, n, seg, seg_id, orient, result) {
    n = split(walk_str, segments, ",")
    result = ""

    for (i = 1; i <= n; i++) {
        seg = segments[i]
        if (length(seg) < 2) continue

        # Extract segment ID and orientation
        seg_id = substr(seg, 1, length(seg) - 1)
        orient = substr(seg, length(seg), 1)

        # VALIDATION: Only forward orientation allowed
        if (orient != "+") {
            print "ERROR: Path '" path_name "' contains reverse orientation '" orient "' for segment '" seg_id "'. Only forward orientation '+' is allowed." > "/dev/stderr"
            error_count++
            return ""
        }

        # Append segment ID (no orientation needed since all are +)
        if (result != "") result = result " "
        result = result seg_id
    }
    return result
}

function normalize_walk_o(walk_str, path_name,    segments, i, n, seg, seg_id, orient, result) {
    n = split(walk_str, segments, " ")
    result = ""

    for (i = 1; i <= n; i++) {
        seg = segments[i]
        if (length(seg) < 2) continue

        seg_id = substr(seg, 1, length(seg) - 1)
        orient = substr(seg, length(seg), 1)

        # VALIDATION: Only forward orientation allowed
        if (orient != "+") {
            print "ERROR: Path '" path_name "' contains reverse orientation '" orient "' for segment '" seg_id "'. Only forward orientation '+' is allowed." > "/dev/stderr"
            error_count++
            return ""
        }

        if (result != "") result = result " "
        result = result seg_id
    }
    return result
}

function normalize_walk_w(walk_str, path_name,    i, j, orient, seg_id, result) {
    result = ""
    i = 1

    while (i <= length(walk_str)) {
        if (substr(walk_str, i, 1) == ">" || substr(walk_str, i, 1) == "<") {
            orient = substr(walk_str, i, 1)

            # VALIDATION: Only forward orientation allowed
            if (orient == "<") {
                # Find segment ID for error message
                j = i + 1
                while (j <= length(walk_str) &&
                       substr(walk_str, j, 1) != ">" &&
                       substr(walk_str, j, 1) != "<") {
                    j++
                }
                seg_id = substr(walk_str, i + 1, j - i - 1)

                print "ERROR: Path '" path_name "' contains reverse orientation '<' for segment '" seg_id "'. Only forward orientation '>' is allowed." > "/dev/stderr"
                error_count++
                return ""
            }

            # Find next orientation marker or end
            j = i + 1
            while (j <= length(walk_str) &&
                   substr(walk_str, j, 1) != ">" &&
                   substr(walk_str, j, 1) != "<") {
                j++
            }

            seg_id = substr(walk_str, i + 1, j - i - 1)
            if (seg_id != "") {
                if (result != "") result = result " "
                result = result seg_id
            }
            i = j
        } else {
            i++
        }
    }
    return result
}

# P lines (GFA 1.0)
# Format: P <path_name> <segment_names> <overlaps>
/^P/ {
    path_name = $2

    # Handle empty path name
    if (path_name == "") {
        print "WARNING: Empty path name at line " NR ", assigning EMPTY_PATH_" NR > "/dev/stderr"
        path_name = "EMPTY_PATH_" NR
        genome_name = "ERROR:EMPTY"
        print path_name, genome_name, ""
        next
    }

    # Resolve genome name
    if (parse_pansn_str(path_name, pa)) {
        genome_name = pa[1]
    } else {
        if (index(path_name, "#")) {
            split(path_name, parts, "#")
            genome_name = parts[1]
        } else if (index(path_name, ".")) {
            split(path_name, parts, ".")
            genome_name = parts[1]
        } else {
            genome_name = "ERROR:" path_name
        }
    }

    # Normalize and validate walk
    normalized_walk = normalize_walk_p($3, path_name)

    # Only output if validation passed
    if (normalized_walk != "" || error_count == 0) {
        print path_name, genome_name, normalized_walk
    }
}

# O lines (GFA 2.0)
# Format: O <path_name> <segment_references>
/^O/ {
    path_name = $2

    if (path_name == "") {
        print "WARNING: Empty path name at line " NR ", assigning EMPTY_PATH_" NR > "/dev/stderr"
        path_name = "EMPTY_PATH_" NR
        genome_name = "ERROR:EMPTY"
        print path_name, genome_name, ""
        next
    }

    # Resolve genome name
    if (parse_pansn_str(path_name, pa)) {
        genome_name = pa[1]
    } else {
        if (index(path_name, "#")) {
            split(path_name, parts, "#")
            genome_name = parts[1]
        } else if (index(path_name, ".")) {
            split(path_name, parts, ".")
            genome_name = parts[1]
        } else {
            genome_name = "ERROR:" path_name
        }
    }

    # Normalize and validate walk
    normalized_walk = normalize_walk_o($3, path_name)

    if (normalized_walk != "" || error_count == 0) {
        print path_name, genome_name, normalized_walk
    }
}

# W lines (GFA 1.1/1.2)
# Format: W <sample> <hap_index> <seq_name> <start> <end> <walk>
/^W/ {
    sample = $2
    hap_index = $3
    seq_name = $4

    if (sample == "") {
        print "WARNING: Empty sample name at line " NR ", skipping" > "/dev/stderr"
        next
    }

    # Construct PanSN-compliant path name: sample#haplotype#sequence
    # genome_name: sample#haplotype (e.g., "hap1#0", "HG002#1")
    # path_name: sample#haplotype#sequence (e.g., "hap1#0#chr1", "HG002#1#1")
    genome_name = sample "#" hap_index
    path_name = sample "#" hap_index "#" seq_name

    # Normalize and validate walk
    normalized_walk = normalize_walk_w($7, path_name)

    if (normalized_walk != "" || error_count == 0) {
        print path_name, genome_name, normalized_walk
    }
}

END {
    if (error_count > 0) {
        print "FATAL: " error_count " path(s) with invalid orientation detected. Build terminated." > "/dev/stderr"
        exit 1
    }
}
