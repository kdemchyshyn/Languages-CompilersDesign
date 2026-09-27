import argparse
import sys

from lexer import lex
from parser import Parser
from semantic_checker import SemanticChecker
from code_generator import CodeGen

parser = argparse.ArgumentParser(description="Compiler Frontend Skeleton")
parser.add_argument("input", help="Path to the input source file (e.g., input.txt)")
parser.add_argument("output", nargs="?", help="Path to the output LLVM IR file (e.g., output.ll)")
parser.add_argument("--tokens", action="store_true", help="Print the generated tokens")
parser.add_argument("--ast", action="store_true", help="Print the generated AST")
args = parser.parse_args()

lines = []
with open(args.input, "rb") as fp:
    lines = lex(fp.read())

if args.tokens:
    for line_tokens in lines:
        for token in line_tokens:
            print(token)
    sys.exit(0)

parser = Parser(lines)
program = parser.parse_program()
if args.ast:
    program.dump()
    sys.exit(0)

if not args.output:
    print("usage: compiler.py [-h] [--tokens] [--ast] input [output]\n" \
    "compiler.py: error: the following arguments are required: output", file=sys.stderr)
    sys.exit(1)

semantic_checker = SemanticChecker()
semantic_checker.visit_program(program)

codegen = CodeGen()
program.accept(codegen)

with open(args.output, "w") as f:
    f.write(str(codegen.module))