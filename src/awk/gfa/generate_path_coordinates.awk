#!/usr/bin/awk -f
# generate_path_coordinates.awk
# High-performance AWK script for generating path_segment_coordinate data
#
# Input:
#   - File 1: segment mapping TSV (original_id \t internal_id \t length)
#   - File 2: GFA file (P/O/W lines)
#
# Output:
#   - STDOUT: path_segment_coordinate TSV (coord_id \t path_id \t segment_id \t coordinate \t segment_order)
#   - path_file: path TSV (PATH \t path_id \t name \t genome_id \t subgraph_id \t length)
#
# Variables (set via -v):
#   - path_file: output file path for path records
#   - subgraph_id: subgraph ID for all paths
#   - next_path_id: starting path ID (default: 1)
#   - next_coord_id: starting coordinate ID (default: 1)
#   - genome_map_file: optional file mapping path_name -> genome_id

BEGIN {
    FS = OFS = "\t"

    # Initialize ID counters
    if (next_path_id == "") next_path_id = 1
    if (next_coord_id == "") next_coord_id = 1
    if (subgraph_id == "") subgraph_id = 1

    path_id_counter = next_path_id
    coord_id_counter = next_coord_id
}

# Phase 1: Load segment mapping (original_id -> internal_id, length)
NR == FNR && FNR > 1 {  # Skip header if exists
    if ($1 != "" && $2 != "" && $3 != "") {
        seg_map[$1] = $2   # original_id -> internal_id
        seg_len[$2] = $3   # internal_id -> length
    }
    next
}

# Phase 2: Load genome mapping if provided (path_name -> genome_id)
FILENAME == genome_map_file && NR != FNR {
    genome_map[$1] = $2
    next
}

# Phase 3: Process GFA path lines
/^P\t/ {
    # GFA 1.0 P line format: P <path_name> <segment_names> <overlaps>
    path_name = $2
    walk_str = $3
    process_p_line(path_name, walk_str)
    next
}

/^O\t/ {
    # GFA 2.0 O line format: O <path_name> <segment_names>
    path_name = $2
    walk_str = $3
    process_o_line(path_name, walk_str)
    next
}

/^W\t/ {
    # GFA 1.1/1.2 W line format: W <sample> <hap_index> <seq_name> <start> <end> <walk>
    sample = $2
    hap_index = $3
    seq_name = $4
    walk_str = $7

    # Construct PanSN-compliant path name: sample#haplotype#sequence
    # This must match the naming in parse_gfa_paths.awk
    path_name = sample "#" hap_index "#" seq_name

    process_w_line(path_name, walk_str)
    next
}

# Function: Process GFA 1.0 P line (comma-separated, orientation suffix)
function process_p_line(pname, walk_str,    n, segments, i, seg, seg_id, orient, internal_id, seg_length, pos, order, total_length) {
    # Split walk string: "s1+,s2-,s3+"
    n = split(walk_str, segments, ",")

    pos = 0
    order = 0
    total_length = 0

    for (i = 1; i <= n; i++) {
        seg = segments[i]
        if (seg == "" || length(seg) < 2) continue

        # Extract segment ID and orientation
        seg_id = substr(seg, 1, length(seg) - 1)
        orient = substr(seg, length(seg))

        # Validate orientation
        if (orient != "+" && orient != "-") continue

        # Map to internal ID
        internal_id = seg_map[seg_id]
        if (internal_id == "") continue  # Skip unknown segments

        seg_length = seg_len[internal_id]
        if (seg_length == "" || seg_length == 0) continue  # Skip zero-length segments

        # Output: coord_id, path_id, segment_id, coordinate (INT8RANGE), segment_order
        print coord_id_counter, path_id_counter, internal_id, "[" pos "," (pos + seg_length) ")", order

        coord_id_counter++
        order++
        pos += seg_length
        total_length = pos
    }

    # Output path record (only if has segments)
    if (order > 0) {
        genome_id = get_genome_id(pname)
        print "PATH", path_id_counter, pname, genome_id, subgraph_id, total_length > path_file
        path_id_counter++
    }
}

# Function: Process GFA 2.0 O line (space-separated, orientation suffix)
function process_o_line(pname, walk_str,    n, segments, i, seg, seg_id, orient, internal_id, seg_length, pos, order, total_length) {
    # Split walk string: "s1+ s2- s3+"
    n = split(walk_str, segments, " ")

    pos = 0
    order = 0
    total_length = 0

    for (i = 1; i <= n; i++) {
        seg = segments[i]
        if (seg == "" || length(seg) < 2) continue

        # Extract segment ID and orientation
        seg_id = substr(seg, 1, length(seg) - 1)
        orient = substr(seg, length(seg))

        if (orient != "+" && orient != "-") continue

        internal_id = seg_map[seg_id]
        if (internal_id == "") continue

        seg_length = seg_len[internal_id]
        if (seg_length == "" || seg_length == 0) continue

        print coord_id_counter, path_id_counter, internal_id, "[" pos "," (pos + seg_length) ")", order

        coord_id_counter++
        order++
        pos += seg_length
        total_length = pos
    }

    if (order > 0) {
        genome_id = get_genome_id(pname)
        print "PATH", path_id_counter, pname, genome_id, subgraph_id, total_length > path_file
        path_id_counter++
    }
}

# Function: Process GFA 1.1/1.2 W line (orientation prefix)
function process_w_line(pname, walk_str,    i, c, seg_id, orient, internal_id, seg_length, pos, order, total_length) {
    # Parse walk string: ">s1>s2<s3" or ">s1<s2>s3"
    pos = 0
    order = 0
    total_length = 0
    seg_id = ""
    orient = ""

    for (i = 1; i <= length(walk_str); i++) {
        c = substr(walk_str, i, 1)

        if (c == ">" || c == "<") {
            # Process previous segment if exists
            if (seg_id != "" && orient != "") {
                internal_id = seg_map[seg_id]
                if (internal_id != "") {
                    seg_length = seg_len[internal_id]
                    if (seg_length != "" && seg_length > 0) {
                        print coord_id_counter, path_id_counter, internal_id, "[" pos "," (pos + seg_length) ")", order

                        coord_id_counter++
                        order++
                        pos += seg_length
                        total_length = pos
                    }
                }
            }

            # Start new segment
            orient = (c == ">") ? "+" : "-"
            seg_id = ""
        } else {
            # Accumulate segment ID
            seg_id = seg_id c
        }
    }

    # Process last segment
    if (seg_id != "" && orient != "") {
        internal_id = seg_map[seg_id]
        if (internal_id != "") {
            seg_length = seg_len[internal_id]
            if (seg_length != "" && seg_length > 0) {
                print coord_id_counter, path_id_counter, internal_id, "[" pos "," (pos + seg_length) ")", order

                coord_id_counter++
                order++
                pos += seg_length
                total_length = pos
            }
        }
    }

    if (order > 0) {
        genome_id = get_genome_id(pname)
        print "PATH", path_id_counter, pname, genome_id, subgraph_id, total_length > path_file
        path_id_counter++
    }
}

# Function: Get genome_id for path
function get_genome_id(pname) {
    # If explicit mapping provided, use it
    if (genome_map_file != "" && pname in genome_map) {
        return genome_map[pname]
    }

    # Return 0 as placeholder (will be resolved by Python)
    return 0
}
