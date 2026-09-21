# Compiler Usage Guide

### Activate env
source ~/lcd/bin/activate

### Compile a source file to LLVM IR
python3 compiler.py input.txt output.ll

### Compile and print lexer tokens
python3 compiler.py input.txt output.ll --tokens

### Execute the generated LLVM IR
llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program
./program

### Run the test suite
./test.sh