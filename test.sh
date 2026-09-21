#!/bin/bash

COMPILER="python3 compiler.py"
PASS_DIR="tests/pass"
FAIL_DIR="tests/fail"
OUTPUT_LL="test_output.ll"

passed=0
failed=0

echo "Running Compiler Tests..."
echo "========================="

echo "Testing valid programs (Expected exit 0 and matching output):"
for test_file in "$PASS_DIR"/*.txt; do
    expected_file="${test_file%.txt}.expected"
    
    ERROR_MSG=$($COMPILER "$test_file" "$OUTPUT_LL" 2>&1 >/dev/null)
    compilation_exit_code=$?

    if [ $compilation_exit_code -eq 0 ]; then
        if command -v lli >/dev/null 2>&1; then
            ACTUAL_OUTPUT=$(lli "$OUTPUT_LL")
            
            if [ -f "$expected_file" ]; then
                EXPECTED_OUTPUT=$(cat "$expected_file")
                
                if [ "$ACTUAL_OUTPUT" = "$EXPECTED_OUTPUT" ]; then
                    echo "  ✅ [PASS] $test_file (Compiled & Output Matched)"
                    passed=$((passed + 1))
                else
                    echo "  ❌ [FAIL] $test_file (Output Mismatch)"
                    echo "     Expected: '$EXPECTED_OUTPUT'"
                    echo "     Got:      '$ACTUAL_OUTPUT'"
                    failed=$((failed + 1))
                fi
            else
                echo "  ⚠️ [WARN] $test_file (Compiled, but $expected_file is missing)"
                passed=$((passed + 1))
            fi
        else
            echo "  ⚠️ [WARN] lli command not found. Skipping execution phase for $test_file."
            passed=$((passed + 1))
        fi
    else
        echo "  ❌ [FAIL] $test_file (Failed to compile)"
        echo "     Output: $ERROR_MSG"
        failed=$((failed + 1))
    fi
done

echo "-------------------------"

echo "Testing invalid programs (Expected compilation error):"
for test_file in "$FAIL_DIR"/*.txt; do
    expected_file="${test_file%.txt}.expected"
    
    # Capture stderr to compare with expected errors
    ERROR_MSG=$($COMPILER "$test_file" "$OUTPUT_LL" 2>&1 >/dev/null)
    compilation_exit_code=$?

    if [ $compilation_exit_code -ne 0 ]; then
        if [ -f "$expected_file" ]; then
            EXPECTED_OUTPUT=$(cat "$expected_file")
            
            if [ "$ERROR_MSG" = "$EXPECTED_OUTPUT" ]; then
                echo "  ✅ [PASS] $test_file correctly failed with expected error."
                passed=$((passed + 1))
            else
                echo "  ❌ [FAIL] $test_file (Error Output Mismatch)"
                echo "     Expected: '$EXPECTED_OUTPUT'"
                echo "     Got:      '$ERROR_MSG'"
                failed=$((failed + 1))
            fi
        else
            echo "  ⚠️ [WARN] $test_file correctly failed, but $expected_file is missing."
            echo "     -> Caught: $ERROR_MSG"
            passed=$((passed + 1))
        fi
    else
        echo "  ❌ [FAIL] $test_file incorrectly compiled! (Expected an error)"
        failed=$((failed + 1))
    fi
done

rm -f "$OUTPUT_LL"

echo "========================="
echo "Test Summary: $passed passed, $failed failed."

if [ $failed -ne 0 ]; then
    exit 1
else
    exit 0
fi