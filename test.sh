#!/bin/bash

OPT_COMPILER="python3 src/compiler.py"
COMPILER="$OPT_COMPILER"
if [ "${REMOVE_UNUSED:-0}" = 1 ]; then
    COMPILER="$COMPILER --remove-unused"
fi
PASS_DIR="tests/ok"
FAIL_DIR="tests/err"
OUTPUT_LL="test_output.ll"
OUTPUT_OPT_LL="test_output_opt.ll"

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
            in_file="${test_file%.txt}.in"
            if [ -f "$in_file" ]; then
                ACTUAL_OUTPUT=$(lli "$OUTPUT_LL" < "$in_file")
            else
                ACTUAL_OUTPUT=$(lli "$OUTPUT_LL")
            fi
            
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
                echo "  ❌ [FAIL] $test_file (Compiled and AST matched, but $expected_file is missing)"
                failed=$((failed + 1))
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
            echo "  ❌ [FAIL] $test_file correctly failed, but $expected_file is missing."
            echo "     -> Caught: $ERROR_MSG"
            failed=$((failed + 1))
        fi
    else
        echo "  ❌ [FAIL] $test_file incorrectly compiled! (Expected an error)"
        failed=$((failed + 1))
    fi
done

echo "-------------------------"
echo "Existing tests/ok + tests/err: $passed passed, $failed failed."
existing_passed=$passed
existing_failed=$failed

echo "Testing optimizations (checked AST, output and exit status, optional definitions):"
for test_file in tests/opt/*.txt; do
    [ -f "$test_file" ] || continue
    expected_ast_file="${test_file%.txt}.astc"
    expected_file="${test_file%.txt}.expected"
    in_file="${test_file%.txt}.in"
    defs_file="${test_file%.txt}.defs"

    ACTUAL_AST=$($OPT_COMPILER --remove-unused --ast-checked "$test_file" 2>&1)
    ast_exit_code=$?
    if [ $ast_exit_code -eq 0 ] && [ -f "$expected_ast_file" ] && \
            [ "$ACTUAL_AST" = "$(cat "$expected_ast_file")" ]; then
        echo "  ✅ [PASS] $test_file (Optimized AST Matched)"
        passed=$((passed + 1))
    else
        echo "  ❌ [FAIL] $test_file (Optimized AST Mismatch or Generation Failed)"
        echo "     Expected AST file: $expected_ast_file"
        echo "     Got AST: '$ACTUAL_AST'"
        failed=$((failed + 1))
    fi

    PLAIN_ERROR=$($OPT_COMPILER "$test_file" "$OUTPUT_LL" 2>&1)
    plain_compilation_exit_code=$?
    OPT_ERROR=$($OPT_COMPILER --remove-unused "$test_file" "$OUTPUT_OPT_LL" 2>&1)
    opt_compilation_exit_code=$?

    if [ $plain_compilation_exit_code -eq 0 ] && [ $opt_compilation_exit_code -eq 0 ] && \
            [ -f "$expected_file" ] && command -v lli >/dev/null 2>&1; then
        # The language exit value is printed on stdout. Compare process statuses
        # separately; a matching nonzero status is not itself a test failure.
        if [ ! -f "$in_file" ]; then
            in_file=/dev/null
        fi
        PLAIN_OUTPUT=$(lli "$OUTPUT_LL" < "$in_file")
        plain_exit_code=$?
        OPT_OUTPUT=$(lli "$OUTPUT_OPT_LL" < "$in_file")
        opt_exit_code=$?
        EXPECTED_OUTPUT=$(cat "$expected_file")
        if [ "$PLAIN_OUTPUT" = "$EXPECTED_OUTPUT" ] && \
                [ "$OPT_OUTPUT" = "$EXPECTED_OUTPUT" ] && \
                [ $plain_exit_code -eq $opt_exit_code ]; then
            echo "  ✅ [PASS] $test_file (Both Outputs & Exit Statuses Matched)"
            passed=$((passed + 1))
        else
            echo "  ❌ [FAIL] $test_file (Output or Exit Status Mismatch)"
            echo "     Expected: '$EXPECTED_OUTPUT'"
            echo "     Without flag (status $plain_exit_code): '$PLAIN_OUTPUT'"
            echo "     With flag (status $opt_exit_code): '$OPT_OUTPUT'"
            failed=$((failed + 1))
        fi
    else
        echo "  ❌ [FAIL] $test_file (Compilation Failed, Missing Expected Output or lli)"
        echo "     Without flag: $PLAIN_ERROR"
        echo "     With flag: $OPT_ERROR"
        failed=$((failed + 1))
    fi

    if [ -f "$defs_file" ]; then
        if [ $opt_compilation_exit_code -eq 0 ]; then
            ACTUAL_DEFS=$(grep '^define' "$OUTPUT_OPT_LL" | sed -E 's/^[^@]*@"?([^"(]+)"?\(.*/\1/')
            EXPECTED_DEFS=$(cat "$defs_file")
        fi
        if [ $opt_compilation_exit_code -eq 0 ] && [ "$ACTUAL_DEFS" = "$EXPECTED_DEFS" ]; then
            echo "  ✅ [PASS] $test_file (Defined Function Names Matched)"
            passed=$((passed + 1))
        else
            echo "  ❌ [FAIL] $test_file (Defined Function Names Mismatch or Compilation Failed)"
            failed=$((failed + 1))
        fi
    fi
done

echo "Optimization checks: $((passed - existing_passed)) passed, $((failed - existing_failed)) failed."
rm -f "$OUTPUT_LL" "$OUTPUT_OPT_LL"

echo "========================="
echo "Test Summary: $passed passed, $failed failed."

if [ $failed -ne 0 ]; then
    exit 1
else
    exit 0
fi
