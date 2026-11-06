# Compiler Usage Guide

### Activate env
source ~/lcd/bin/activate

### Compile a source file to LLVM IR
python3 src/compiler.py input.txt output.ll

### Print lexer tokens
python3 src/compiler.py --tokens input.txt

### Print AST
python3 src/compiler.py --ast input.txt

### Print the AST after the semantic pass
python3 src/compiler.py --ast-checked input.txt

### Compile with unused code removal
python3 src/compiler.py input.txt --remove-unused output.ll

The flag may appear before, between, or after the input and output paths.

### Execute the generated LLVM IR
llc -filetype=obj -relocation-model=pic output.ll -o output.o<br>
clang -fPIE output.o -o program <br>
./program

### Run the test suite
./test.sh


## Optimizations

The pass removes unused variables per declaration, together with their assignments.
It removes unused global functions too. Both removals repeat until the checked AST stops changing.

A variable that only feeds itself (`k := k + 1`) survives.
Self-recursive functions and functions that call only each other also survive.

The compiler is written in Python and runs here on CPython.
Reference counting releases objects when their last strong reference disappears. The cyclic collector reclaims unreachable cycles.
AST nodes have no parent pointers. A strong parent pointer would increase the parent's reference count. It could also form a cycle with the child links.
A live checker keeps top-level declarations in `scopes[0]`, even after pruning and `gc.collect()`.
These measurements concern the compiler's AST memory.

One measurement from `python3 tests/unit/weakref_check.py`:

```text
checker alive, immediately: block freed=True, top-level freed=False
```
