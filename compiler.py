import argparse
from os import name
import sys
from llvmlite import ir
import llvmlite.binding as llvm

KEYWORDS = {b"i32": "keyword", b"mut": "keyword", b"exit": "keyword"}

def CompileError(message):
    print("compilation error: " + message, file=sys.stderr)
    sys.exit(1)

class Token:
    def __init__(self, kind, text, line, col):
        self.kind = kind
        self.text = text
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.kind}, '{self.text}', {self.line}:{self.col})"

def is_alpha(b):
    if b > 127: return False
    return b is not None and (chr(b).isalpha() or chr(b) == '_')

def is_digit(b):
    if b > 127: return False
    return b is not None and chr(b).isdigit()

def lex(data: bytes):
    lines, tokens = [], []
    state, start, line, col = "START", 0, 1, 1
    blocks = 0
    i = 0
    while i <= len(data): # one extra step: the end of input
        b = data[i] if i < len(data) else None
        if state == "START":
            if b is None: 
                if blocks > 0: raise CompileError(f"line {line}:{col}: {repr("{")} is not closed before the end of the line")
                else: break
            elif b in (32, 9): pass # space, tab
            elif b == 10: 
                if blocks > 0: raise CompileError(f"line {line}:{col}: {repr("{")} is not closed before the end of the line")
                elif tokens: lines.append(tokens); tokens = []; line += 1; col = 0
            elif is_alpha(b): state, start = "IDENT", i
            elif is_digit(b): state, start = "NUMBER", i
            elif b == ord("{"): tokens.append(Token("lbrace", "{", line, col)); blocks += 1
            elif b == ord("+"): tokens.append(Token("operation", "+", line, col))
            elif b == ord("-"): tokens.append(Token("operation", "-", line, col))
            elif b == ord("*"): tokens.append(Token("operation", "*", line, col))
            elif b == ord("}"): 
                tokens.append(Token("rbrace", "}", line, col))
                if blocks == 0: raise CompileError(f"line {line}:{col}: {repr("}")} is not opened in the line") 
                else: blocks -= 1
            elif b == ord(":"): state, start = "ASSIGN", i
            else: raise CompileError(f"line {line}:{col}: unexpected byte {repr(chr(b))}")
        elif state == "IDENT":
            if b is not None and (is_alpha(b) or is_digit(b)): pass
            else:
                word = data[start:i]
                tokens.append(Token(KEYWORDS.get(word, "ident"), word.decode(), line, col - len(word)))
                state = "START"; continue # re-read this byte in START
        elif state == "NUMBER": 
            if b is not None and is_digit(b): pass
            elif b is not None and is_alpha(b): raise CompileError(f"line {line}:{col}: a letter inside a number {data[start:i+1].decode()}")
            else:
                number = data[start:i]
                tokens.append(Token("number", number.decode(), line, col - len(number)))
                state = "START"; continue # re-read this byte in START
        elif state == "ASSIGN": 
            if b == ord("="): tokens.append(Token("assign", ":=", line, col - 1)); state = "START"
            else: raise CompileError(f"line {line}:{col}: a {repr(":")} not followed by {repr("=")}")
        i += 1; col += 1
    if tokens: lines.append(tokens)
    return lines

def parse_expression(builder, tokens):
    if not tokens:
        raise CompileError("missing expression")
        
    def get_val(token):
        if token.kind == "number":
            return ir.Constant(I32, int(token.text))
        elif token.kind == "ident":
            if token.text in mut_vars:
                return builder.load(mut_vars[token.text])
            elif token.text in const_vars:
                return builder.load(const_vars[token.text])
            else:
                raise CompileError(f"line {token.line}:{token.col}: variable '{token.text}' is used before its declaration")
        raise CompileError(f"line {token.line}:{token.col}: invalid value '{token.text}'")

    if tokens[0].kind == "operation" and tokens[0].text == "-":
        if len(tokens) < 2:
            raise CompileError(f"line {tokens[0].line}:{tokens[0].col}: missing value after unary minus")
        val = get_val(tokens[1])
        return builder.neg(val)

    val1 = get_val(tokens[0])

    if len(tokens) == 1:
        return val1

    if len(tokens) == 3 and tokens[1].kind == "operation":
        op = tokens[1].text
        val2 = get_val(tokens[2])
        if op == "+": return builder.add(val1, val2)
        elif op == "-": return builder.sub(val1, val2)
        elif op == "*": return builder.mul(val1, val2)

    raise CompileError(f"line {tokens[0].line}:{tokens[0].col}: invalid expression syntax")

def parse_declaration(builder, line):
    i = 1
    is_mut = False
    
    if i < len(line) and line[i].kind == "keyword" and line[i].text == "mut":
        is_mut = True
        i += 1

    if i >= len(line) or line[i].kind != "ident":
        col = line[i-1].col if i > 0 else 1
        raise CompileError(f"line {line[0].line}:{col}: missing or invalid variable name")
    
    name_token = line[i]
    name = name_token.text
    if name in mut_vars or name in const_vars:
        raise CompileError(f"line {name_token.line}:{name_token.col}: variable '{name}' is already defined")
    i += 1

    if i >= len(line) or line[i].kind != "lbrace":
        raise CompileError(f"line {name_token.line}:{name_token.col}: variable '{name}' needs an initialiser in {{}}")
    i += 1

    # Find the matching right brace
    expr_tokens = []
    while i < len(line) and line[i].kind != "rbrace":
        expr_tokens.append(line[i])
        i += 1
        
    if i >= len(line) or line[i].kind != "rbrace":
        raise CompileError(f"line {name_token.line}:{name_token.col}: missing closing {repr('}')} for initialiser")
    
    if i + 1 < len(line):
        raise CompileError(f"line {line[i+1].line}:{line[i+1].col}: extra tokens on a line")

    value = parse_expression(builder, expr_tokens)
    
    ptr = builder.alloca(I32, name=name)
    builder.store(value, ptr)
    
    if is_mut:
        mut_vars[name] = ptr
    else:
        const_vars[name] = ptr

def parse_assignment(builder, line):
    name_token = line[0]
    name = name_token.text

    if name not in mut_vars:
        if name in const_vars:
            raise CompileError(f"line {name_token.line}:{name_token.col}: cannot assign to '{name}': it is not mut")
        raise CompileError(f"line {name_token.line}:{name_token.col}: variable '{name}' is not defined")

    if len(line) < 2 or line[1].kind != "assign":
        raise CompileError(f"line {name_token.line}:{name_token.col}: expected ':=' after variable")

    expr_tokens = line[2:]
    if not expr_tokens:
        raise CompileError(f"line {line[1].line}:{line[1].col}: nothing to assign")

    value = parse_expression(builder, expr_tokens)
    builder.store(value, mut_vars[name])

def parse_exit(builder, line):
    if len(line) < 2:
        raise CompileError(f"line {line[0].line}:{line[0].col}: exit requires a value")

    expr_tokens = line[1:]
    value = parse_expression(builder, expr_tokens)
    
    builder.call(printf, [builder.bitcast(fmt, ir.PointerType(I8)), value])
    builder.ret(ir.Constant(I32, 0))


parser = argparse.ArgumentParser(description="Compiler Frontend Skeleton")
parser.add_argument("input", help="Path to the input source file (e.g., input.txt)")
parser.add_argument("output", help="Path to the output LLVM IR file (e.g., output.ll)")
parser.add_argument("--tokens", action="store_true", help="Print the generated tokens")
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

const_vars, mut_vars = {}, {}
exit_calls = 0

for line in lines:
    if not line: continue
    first = line[0]

    if exit_calls > 0:
        raise CompileError(f"line {first.line}:{first.col}: statement after exit")

    if first.text == "i32":
        parse_declaration(builder, line)
    elif first.text == "exit":
        parse_exit(builder, line)
        exit_calls += 1
    elif first.kind == "ident":
        parse_assignment(builder, line)
    else:
        raise CompileError(f"line {first.line}:{first.col}: invalid statement")

if exit_calls == 0:
    raise CompileError(f"line {len(lines) + 1}:1: program needs an exit statement")

with open(args.output, "w") as f:
    f.write(str(module))