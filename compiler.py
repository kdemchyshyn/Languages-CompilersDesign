import argparse
import sys
from llvmlite import ir
import llvmlite.binding as llvm

variables = {} # name -> alloca

def compilation_error(line, message):
    print(f"compilation error: line {line}: {message}", file=sys.stderr)
    sys.exit(1)

def is_valid_int(val: str):
    # Supports both "5" and "-5"
    return val.isdigit() or (val.startswith("-") and val[1:].isdigit())

def declarateVar(builder, name: str, lineCnt):
    if len(name.split()) > 1: 
        compilation_error(lineCnt, "extra symbols after declaration")

    if not (name[0].isalpha() or name[0] == "_"): 
        compilation_error(lineCnt, "variable must start with letter or _")

    for symbol in name: 
        if not (symbol.isalpha() or symbol.isdigit() or symbol == "_"):
            compilation_error(lineCnt, "variable can contain only letters, digits and _")

    if name == "int" or name == "exit": 
        compilation_error(lineCnt, "word reserved")

    if name in variables: 
        compilation_error(lineCnt, "variable already declared")

    variables[name] = builder.alloca(I32, name=name)

def defineVar(builder, line: str, lineCnt):
    line = line.replace(" ", "")

    if ":=" not in line:
        compilation_error(lineCnt, "uncomplete definition, :=")

    tokens = line.split(":=")

    if len(tokens) != 2:  
        compilation_error(lineCnt, "too many definitions in one line")

    name = tokens[0]
    expr = tokens[1]
    
    if name not in variables:  
        compilation_error(lineCnt, "unknown variable")

    val1_str = ""
    val2_str = ""
    opr = ""
    
    for symbol in expr:
        if symbol in {"+", "-", "*"}:
            # Handle negative numbers at the start of expression (e.g., x := -5)
            if symbol == "-" and val1_str == "":
                val1_str += symbol
                continue
                
            if opr:
                compilation_error(lineCnt, "too many operations")
            opr = symbol
            continue

        if not (symbol.isalpha() or symbol.isdigit() or symbol == "_"):
            compilation_error(lineCnt, "wrong symbols")

        if opr: 
            val2_str += symbol
        else:
            val1_str += symbol

    # --- Convert string 1 to LLVM ---
    if val1_str in variables:
        val1_ir = builder.load(variables[val1_str])
    else:
        if not is_valid_int(val1_str):
            compilation_error(lineCnt, "value has to be variable or int")
        val1_ir = ir.Constant(I32, int(val1_str))

    # If simple assignment
    if opr == "":
        builder.store(val1_ir, variables[name])
        return

    # --- Convert string 2 to LLVM ---
    if val2_str in variables:
        val2_ir = builder.load(variables[val2_str])
    else:
        if not is_valid_int(val2_str):
            compilation_error(lineCnt, "value has to be variable or int")
        val2_ir = ir.Constant(I32, int(val2_str))

    # Apply operations
    if opr == "+":
        builder.store(builder.add(val1_ir, val2_ir), variables[name])
    elif opr == "-":
        builder.store(builder.sub(val1_ir, val2_ir), variables[name])
    elif opr == "*":
        builder.store(builder.mul(val1_ir, val2_ir), variables[name])
    else:
        compilation_error(lineCnt, "wrong definition")


def exitProgram(builder, value: str, lineCnt):
    if is_valid_int(value):
        builder.call(printf, [builder.bitcast(fmt, ir.PointerType(I8)), ir.Constant(I32, int(value))])
        builder.ret(ir.Constant(I32, 0))
        return

    if value in variables:
        builder.call(printf, [builder.bitcast(fmt, ir.PointerType(I8)), builder.load(variables[value])])
        builder.ret(ir.Constant(I32, 0))
        return

    compilation_error(lineCnt, "program must return value")


parser = argparse.ArgumentParser(description="Compiler Frontend Skeleton")
parser.add_argument("input", help="Path to the input source file (e.g., input.txt)")
parser.add_argument("output", help="Path to the output LLVM IR file (e.g., output.ll)")
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

lineCnt = 0
exitCalls = 0

with open(args.input, "r") as fp:
    for raw_line in fp:
        lineCnt += 1
        
        # Prevent empty line crashes
        if not raw_line.strip():
            continue
            
        line = " ".join(raw_line.split()) + "\n"

        if exitCalls != 0:
            compilation_error(lineCnt, "exit has been called")

        token = ""
        for i in range(len(line)):
            if line[i] == " ":
                if token == "int":
                    declarateVar(builder, line[i+1:].strip(), lineCnt)
                    break
                elif token == "exit":
                    exitProgram(builder, line[i+1:].strip(), lineCnt)
                    exitCalls += 1
                    break
            elif line[i] == ":":
                defineVar(builder, line.strip(), lineCnt)
                break
            elif line[i] == "\n":
                compilation_error(lineCnt, "no valid action")
            
            token += line[i]

if exitCalls != 1:
    compilation_error(lineCnt, "program must exit once")

with open(args.output, "w") as f:
    f.write(str(module))