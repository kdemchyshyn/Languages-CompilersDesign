import argparse
from os import name
import sys
from llvmlite import ir
import llvmlite.binding as llvm

from errors import CompileError
from lexer import lex
from parser import Parser
from code_generator import CodeGen

def CompileError(message):
    print("compilation error: " + message, file=sys.stderr)
    sys.exit(1)

parser = argparse.ArgumentParser(description="Compiler Frontend Skeleton")
parser.add_argument("input", help="Path to the input source file (e.g., input.txt)")
parser.add_argument("output", help="Path to the output LLVM IR file (e.g., output.ll)")
parser.add_argument("--tokens", action="store_true", help="Print the generated tokens")
parser.add_argument("--ast", action="store_true", help="Print the generated AST")
args = parser.parse_args()

I32, I8 = ir.IntType(32), ir.IntType(8)

module = ir.Module(name="practice1")
module.triple = llvm.get_default_triple()
main = ir.Function(module, ir.FunctionType(I32, []), name="main")
builder = ir.IRBuilder(main.append_basic_block("entry"))

printf = ir.Function(module, ir.FunctionType(I32, [ir.PointerType(I8)], var_arg=True), name="printf")
text = b"Program exit with result %d\n\0"
fmt = ir.GlobalVariable(module, ir.ArrayType(I8, len(text)), name="fmt")
fmt.linkage, fmt.global_constant = "private", True
fmt.initializer = ir.Constant(ir.ArrayType(I8, len(text)), bytearray(text))

lines = []
with open(args.input, "rb") as fp:
    lines = lex(fp.read())

if args.tokens:
    for line_tokens in lines:
        for token in line_tokens:
            print(token)

parser = Parser(lines)
program = parser.parse_program()
if args.ast:
    program.dump()

codegen = CodeGen(builder, printf, fmt)
program.accept(codegen)

with open(args.output, "w") as f:
    f.write(str(module))