#!/bin/bash

COMPILER="python3 compiler.py"
PASS_DIR="tests/ok"
FAIL_DIR="tests/err"
OUTPUT_LL="test_output.ll"

passed=0
failed=0

echo "Running Compiler Tests..."
echo "========================="

echo "Testing valid programs (Expected exit 0, matching AST and matching output):"
for test_file in "$PASS_DIR"/*.txt; do
    expected_file="${test_file%.txt}.expected"
    expected_ast_file="${test_file%.txt}.ast"
    
    ACTUAL_AST=$($COMPILER --ast "$test_file" 2>&1)
    ast_exit_code=$?

    ERROR_MSG=$($COMPILER "$test_file" "$OUTPUT_LL" 2>&1 >/dev/null)
    compilation_exit_code=$?

    if [ $ast_exit_code -eq 0 ] && [ $compilation_exit_code -eq 0 ]; then
        if [ -f "$expected_ast_file" ]; then
            EXPECTED_AST=$(cat "$expected_ast_file")
            if [ "$ACTUAL_AST" != "$EXPECTED_AST" ]; then
                echo "  ❌ [FAIL] $test_file (AST Mismatch)"
                echo "     Expected AST: '$EXPECTED_AST'"
                echo "     Got AST:      '$ACTUAL_AST'"
                failed=$((failed + 1))
                continue # Skip the execution check if the AST is already wrong
            fi
        else
            echo "  ⚠️ [WARN] $test_file (Missing $expected_ast_file)"
        fi

        if command -v lli >/dev/null 2>&1; then
            ACTUAL_OUTPUT=$(lli "$OUTPUT_LL")
            
            if [ -f "$expected_file" ]; then
                EXPECTED_OUTPUT=$(cat "$expected_file")
                
                if [ "$ACTUAL_OUTPUT" = "$EXPECTED_OUTPUT" ]; then
                    echo "  ✅ [PASS] $test_file (Compiled, AST & Output Matched)"
                    passed=$((passed + 1))
                else
                    echo "  ❌ [FAIL] $test_file (Output Mismatch)"
                    echo "     Expected: '$EXPECTED_OUTPUT'"
                    echo "     Got:      '$ACTUAL_OUTPUT'"
                    failed=$((failed + 1))
                fi
            else
                echo "  ⚠️ [WARN] $test_file (Compiled and AST matched, but $expected_file is missing)"
                passed=$((passed + 1))
            fi
        else
            echo "  ⚠️ [WARN] lli command not found. Skipping execution phase for $test_file."
            passed=$((passed + 1))
        fi
    else
        echo "  ❌ [FAIL] $test_file (Failed to compile or generate AST)"
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