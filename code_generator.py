from llvmlite import ir
from errors import CompileError

class CodeGen:
    def __init__(self, builder, printf_func, fmt_str):
        self.builder = builder
        self.printf = printf_func
        self.fmt = fmt_str
        self.env = {}  # Maps name -> {"ptr": ptr, "mutable": bool}

    def error(self, node, message):
        raise CompileError(f"line {node.line}:{node.col}: {message}")

    def visit_program(self, node):
        for stmt in node.statements:
            stmt.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        if node.name in self.env:
            self.error(node, f"variable '{node.name}' is already declared")
            
        init_val = node.init.accept(self)
        
        # Allocate stack space and store the initial value
        ptr = self.builder.alloca(ir.IntType(32), name=node.name)
        self.builder.store(init_val, ptr)
        
        # Save to symbol table
        self.env[node.name] = {"ptr": ptr, "mutable": node.mutable}

    def visit_assign(self, node):
        if node.name not in self.env:
            self.error(node, f"variable '{node.name}' is not declared")
            
        var_info = self.env[node.name]
        if not var_info["mutable"]:
            self.error(node, f"cannot assign to constant variable '{node.name}'")
            
        val = node.value.accept(self)
        self.builder.store(val, var_info["ptr"])

    def visit_exit(self, node):
        val = node.value.accept(self)
        
        # Cast the format string array to an i8* pointer for printf
        fmt_ptr = self.builder.bitcast(self.fmt, ir.PointerType(ir.IntType(8)))
        self.builder.call(self.printf, [fmt_ptr, val])
        
        # Return 0 from main
        self.builder.ret(ir.Constant(ir.IntType(32), 0))

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)
        
        if node.op == "+":
            return self.builder.add(left, right, name="addtmp")
        elif node.op == "-":
            return self.builder.sub(left, right, name="subtmp")
        elif node.op == "*":
            return self.builder.mul(left, right, name="multmp")
        else:
            self.error(node, f"unknown operator '{node.op}'")

    def visit_var(self, node):
        if node.name not in self.env:
            self.error(node, f"variable '{node.name}' is not declared")
            
        ptr = self.env[node.name]["ptr"]
        return self.builder.load(ptr, name=node.name)

    def visit_const(self, node):
        return ir.Constant(ir.IntType(32), node.value)