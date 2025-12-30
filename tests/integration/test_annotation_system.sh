#!/bin/bash
# Integration Test Suite for HAP Annotation System
# Tests end-to-end workflows for annotation import, query, edit, delete, and export

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test database connection
DB_HOST="127.0.0.1"
DB_USER="hap"
DB_NAME="hap"
DB_PASSWORD="hap"

# Test data directory
TEST_DATA_DIR="data/mini-example"
TEST_OUTPUT_DIR="/tmp/hap_annotation_tests"

# Helper functions
print_test() {
    echo -e "\n${YELLOW}[TEST $1]${NC} $2"
    TESTS_RUN=$((TESTS_RUN + 1))
}

print_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_summary() {
    echo -e "\n${YELLOW}========================================${NC}"
    echo -e "${YELLOW}TEST SUMMARY${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo -e "Total tests run: $TESTS_RUN"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}All tests passed!${NC}"
        return 0
    else
        echo -e "\n${RED}Some tests failed!${NC}"
        return 1
    fi
}

# Database helper
db_query() {
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "$1" 2>&1
}

# Setup
setup() {
    echo -e "${YELLOW}Setting up test environment...${NC}"

    # Create output directory
    mkdir -p "$TEST_OUTPUT_DIR"

    # Clean up any existing test annotations
    db_query "DELETE FROM annotation WHERE path_id IN (
        SELECT p.id FROM path p
        JOIN genome g ON p.genome_id = g.id
        WHERE g.name LIKE 'test_%'
    );" > /dev/null 2>&1 || true

    db_query "DELETE FROM genome WHERE name LIKE 'test_%';" > /dev/null 2>&1 || true

    echo -e "${GREEN}Setup complete${NC}"
}

# Cleanup
cleanup() {
    echo -e "\n${YELLOW}Cleaning up test environment...${NC}"

    # Remove test files
    rm -rf "$TEST_OUTPUT_DIR"

    # Clean up test data from database
    db_query "DELETE FROM annotation WHERE path_id IN (
        SELECT p.id FROM path p
        JOIN genome g ON p.genome_id = g.id
        WHERE g.name LIKE 'test_%'
    );" > /dev/null 2>&1 || true

    db_query "DELETE FROM genome WHERE name LIKE 'test_%';" > /dev/null 2>&1 || true

    echo -e "${GREEN}Cleanup complete${NC}"
}

# Test 1: GFF3 Import
test_gff3_import() {
    print_test 1 "GFF3 Import"

    local test_file="$TEST_DATA_DIR/smp1.annotations.gff3"

    if [ ! -f "$test_file" ]; then
        print_fail "Test file not found: $test_file"
        return 1
    fi

    # Import
    local output=$(poetry run hap annotation add \
        --file "$test_file" \
        --genome-name smp1 \
        --haplotype-index 0 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "Successfully imported"; then
        local count=$(echo "$output" | grep -oP 'Successfully imported \K\d+')
        if [ "$count" -gt 0 ]; then
            print_pass "Imported $count annotations from GFF3"
        else
            print_fail "No annotations imported"
        fi
    else
        print_fail "Import failed: $output"
    fi
}

# Test 2: GTF Import
test_gtf_import() {
    print_test 2 "GTF Import"

    local test_file="$TEST_DATA_DIR/smp1.annotations.gtf"

    if [ ! -f "$test_file" ]; then
        print_fail "Test file not found: $test_file"
        return 1
    fi

    # Import
    local output=$(poetry run hap annotation add \
        --file "$test_file" \
        --genome-name smp1 \
        --format gtf 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "Successfully imported"; then
        print_pass "GTF import successful"
    else
        print_fail "GTF import failed: $output"
    fi
}

# Test 3: BED Import
test_bed_import() {
    print_test 3 "BED Import"

    local test_file="$TEST_DATA_DIR/smp1.annotations.bed"

    if [ ! -f "$test_file" ]; then
        print_fail "Test file not found: $test_file"
        return 1
    fi

    # Import
    local output=$(poetry run hap annotation add \
        --file "$test_file" \
        --genome-name smp1 \
        --format bed 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "Successfully imported"; then
        print_pass "BED import successful"
    else
        print_fail "BED import failed: $output"
    fi
}

# Test 4: Query by Type
test_query_by_type() {
    print_test 4 "Query by Type"

    local output=$(poetry run hap annotation get --type gene 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "gene"; then
        local count=$(echo "$output" | grep -c "gene" || echo "0")
        print_pass "Found $count gene annotations"
    else
        print_fail "No gene annotations found"
    fi
}

# Test 5: Query by Path
test_query_by_path() {
    print_test 5 "Query by Path"

    local output=$(poetry run hap annotation get --path "smp1#0#1" 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "smp1#0#1"; then
        print_pass "Query by path successful"
    else
        print_fail "Query by path failed"
    fi
}

# Test 6: Query by Label
test_query_by_label() {
    print_test 6 "Query by Label"

    local output=$(poetry run hap annotation get --label "TEST_GENE_1" 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "TEST_GENE_1"; then
        print_pass "Found annotation by label"
    else
        print_fail "Label query failed"
    fi
}

# Test 7: GFF3 Export
test_gff3_export() {
    print_test 7 "GFF3 Export"

    local output_file="$TEST_OUTPUT_DIR/export_test.gff3"

    poetry run hap annotation export \
        --path "smp1#0#1" \
        --format gff3 \
        --output "$output_file" 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null

    if [ -f "$output_file" ]; then
        if head -1 "$output_file" | grep -q "##gff-version 3"; then
            local line_count=$(wc -l < "$output_file")
            print_pass "Exported GFF3 with $line_count lines"
        else
            print_fail "Invalid GFF3 header"
        fi
    else
        print_fail "Export file not created"
    fi
}

# Test 8: GTF Export
test_gtf_export() {
    print_test 8 "GTF Export"

    local output_file="$TEST_OUTPUT_DIR/export_test.gtf"

    poetry run hap annotation export \
        --path "smp1#0#1" \
        --format gtf \
        --output "$output_file" 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        print_pass "GTF export successful"
    else
        print_fail "GTF export failed"
    fi
}

# Test 9: BED Export
test_bed_export() {
    print_test 9 "BED Export"

    local output_file="$TEST_OUTPUT_DIR/export_test.bed"

    poetry run hap annotation export \
        --path "smp1#0#1" \
        --format bed \
        --output "$output_file" 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        local line_count=$(wc -l < "$output_file")
        print_pass "Exported BED with $line_count lines"
    else
        print_fail "BED export failed"
    fi
}

# Test 10: Edit Annotation
test_edit_annotation() {
    print_test 10 "Edit Annotation"

    # Find an annotation ID
    local ann_id=$(poetry run hap annotation get --type gene --path "smp1#0#1" 2>&1 | \
        grep -v "poetry.dev-dependencies" | \
        grep "smp1#0#1" | \
        head -1 | \
        awk '{print $1}')

    if [ -z "$ann_id" ]; then
        print_fail "Could not find annotation to edit"
        return 1
    fi

    # Edit
    local output=$(poetry run hap annotation edit \
        --id "$ann_id" \
        --label "EDITED_GENE" 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "Successfully updated"; then
        # Verify edit
        local check=$(poetry run hap annotation get --id "$ann_id" 2>&1 | grep "EDITED_GENE")
        if [ -n "$check" ]; then
            print_pass "Annotation edited successfully"
        else
            print_fail "Edit not reflected in database"
        fi
    else
        print_fail "Edit failed: $output"
    fi
}

# Test 11: Delete Annotation
test_delete_annotation() {
    print_test 11 "Delete Annotation"

    # Find an annotation ID
    local ann_id=$(poetry run hap annotation get --label "EDITED_GENE" 2>&1 | \
        grep -v "poetry.dev-dependencies" | \
        grep "smp1#0#1" | \
        head -1 | \
        awk '{print $1}')

    if [ -z "$ann_id" ]; then
        print_fail "Could not find annotation to delete"
        return 1
    fi

    # Delete
    local output=$(poetry run hap annotation delete \
        --id "$ann_id" \
        --confirm 2>&1 | grep -v "poetry.dev-dependencies")

    if echo "$output" | grep -q "Successfully deleted"; then
        # Verify deletion
        local check=$(poetry run hap annotation get --id "$ann_id" 2>&1 | grep "$ann_id" | wc -l)
        if [ "$check" -eq 0 ]; then
            print_pass "Annotation deleted successfully"
        else
            print_fail "Annotation still exists after deletion"
        fi
    else
        print_fail "Delete failed: $output"
    fi
}

# Test 12: Coordinate Conversion (Round-trip)
test_coordinate_conversion() {
    print_test 12 "Coordinate Conversion (Round-trip)"

    # Create test GFF3 with known coordinates
    local test_file="$TEST_OUTPUT_DIR/coord_test.gff3"
    cat > "$test_file" <<EOF
##gff-version 3
chr1	test	gene	1000	2000	.	+	.	ID=coord_test;Name=COORD_TEST
EOF

    # Import (1-based → 0-based)
    poetry run hap annotation add \
        --file "$test_file" \
        --genome-name smp1 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null

    # Export (0-based → 1-based)
    local export_file="$TEST_OUTPUT_DIR/coord_export.gff3"
    poetry run hap annotation export \
        --path "smp1#0#1" \
        --format gff3 \
        --output "$export_file" 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null

    # Check if coordinates match
    if grep -q "1000	2000" "$export_file"; then
        print_pass "Coordinate round-trip successful (1000-2000)"
    else
        print_fail "Coordinate conversion error"
        grep "COORD_TEST" "$export_file" || echo "Not found in export"
    fi
}

# Test 13: Multi-format Import for Same Genome
test_multi_format_import() {
    print_test 13 "Multi-format Import for Same Genome"

    # Count annotations before
    local before=$(db_query "SELECT COUNT(*) FROM annotation a JOIN path p ON a.path_id = p.id JOIN genome g ON p.genome_id = g.id WHERE g.name = 'smp1';" | tr -d ' ')

    # Import all formats
    poetry run hap annotation add --file "$TEST_DATA_DIR/smp1.annotations.gff3" --genome-name smp1 2>&1 > /dev/null
    poetry run hap annotation add --file "$TEST_DATA_DIR/smp1.annotations.gtf" --genome-name smp1 --format gtf 2>&1 > /dev/null
    poetry run hap annotation add --file "$TEST_DATA_DIR/smp1.annotations.bed" --genome-name smp1 --format bed 2>&1 > /dev/null

    # Count annotations after
    local after=$(db_query "SELECT COUNT(*) FROM annotation a JOIN path p ON a.path_id = p.id JOIN genome g ON p.genome_id = g.id WHERE g.name = 'smp1';" | tr -d ' ')

    if [ "$after" -gt "$before" ]; then
        print_pass "Multi-format import successful (before: $before, after: $after)"
    else
        print_fail "Multi-format import failed (before: $before, after: $after)"
    fi
}

# Test 14: Query Performance
test_query_performance() {
    print_test 14 "Query Performance"

    local start=$(date +%s%N)
    poetry run hap annotation get --type gene 2>&1 | grep -v "poetry.dev-dependencies" > /dev/null
    local end=$(date +%s%N)

    local duration=$(( (end - start) / 1000000 )) # Convert to milliseconds

    if [ "$duration" -lt 5000 ]; then # Less than 5 seconds
        print_pass "Query completed in ${duration}ms"
    else
        print_fail "Query took too long: ${duration}ms"
    fi
}

# Test 15: Database Integrity
test_database_integrity() {
    print_test 15 "Database Integrity"

    # Check for orphaned annotations
    local orphaned=$(db_query "SELECT COUNT(*) FROM annotation WHERE path_id NOT IN (SELECT id FROM path);" | tr -d ' ')

    if [ "$orphaned" -eq 0 ]; then
        print_pass "No orphaned annotations"
    else
        print_fail "Found $orphaned orphaned annotations"
    fi

    # Check foreign key constraints
    local fk_errors=$(db_query "SELECT COUNT(*) FROM annotation a LEFT JOIN path p ON a.path_id = p.id WHERE p.id IS NULL;" | tr -d ' ')

    if [ "$fk_errors" -eq 0 ]; then
        print_pass "Foreign key constraints valid"
    else
        print_fail "Found $fk_errors foreign key constraint violations"
    fi
}

# Main execution
main() {
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}HAP ANNOTATION INTEGRATION TESTS${NC}"
    echo -e "${YELLOW}========================================${NC}"

    # Setup
    setup

    # Run tests
    test_gff3_import
    test_gtf_import
    test_bed_import
    test_query_by_type
    test_query_by_path
    test_query_by_label
    test_gff3_export
    test_gtf_export
    test_bed_export
    test_edit_annotation
    test_delete_annotation
    test_coordinate_conversion
    test_multi_format_import
    test_query_performance
    test_database_integrity

    # Cleanup
    cleanup

    # Summary
    print_summary

    return $?
}

# Run main
main
exit $?
