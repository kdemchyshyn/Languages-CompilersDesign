# Compiler Usage Guide

### Activate env
source ~/lcd/bin/activate

### Compile a source file to LLVM IR
python3 compiler.py input.txt output.ll

### Print lexer tokens
python3 compiler.py --tokens input.txt

### Print AST
python3 compiler.py --ast input.txt

### Execute the generated LLVM IR
llc -filetype=obj -relocation-model=pic output.ll -o output.o<br>
clang -fPIE output.o -o program <br>
./program

### Run the test suite
./test.sh