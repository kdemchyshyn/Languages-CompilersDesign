from errors import CompileError
from nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode, BoolNode,
    BlockNode, IfNode, NotNode
)

I32_MAX = 2147483647
I32_MIN = -2147483648
I64_MAX = 9223372036854775807
I64_MIN = -9223372036854775808


class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]  # name -> DeclNode

    def error(self, node, message):
        raise CompileError(f"line {node.line}:{node.col}: {message}")

    def lookup(self, node, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name]
        self.error(node, f"variable '{name}' is used before its declaration")

    def check_assignable(self, expr, want, at, what):
        have = expr.type
        if have == want or (have == "i32" and want == "i64"):
            return
        if isinstance(expr, ConstNode) and want == "i32" and have == "i64":
            self.error(expr, f"constant {expr.value} does not fit in i32")
        self.error(at, f"cannot {what} of type {want} with a value of type {have}")

    def visit_program(self, node):
        for stmt in node.statements:
            stmt.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        if node.name in self.scopes[-1]:
            self.error(node, f"variable '{node.name}' is already declared in this block")
            
        node.init.accept(self)
        self.check_assignable(node.init, node.type_name, node, f"initialise '{node.name}'")
        self.scopes[-1][node.name] = node

    def visit_assign(self, node):
        decl = self.lookup(node, node.name)
        if not decl.mutable:
            self.error(node, f"cannot assign to constant variable '{node.name}'")
        node.decl = decl
        node.value.accept(self)
        self.check_assignable(
            node.value, decl.type_name, node, f"assign to '{node.name}'"
        )

    def visit_exit(self, node):
        node.value.accept(self)

    def visit_binop(self, node):
        lt = node.left.accept(self)
        rt = node.right.accept(self)

        if node.op in ("+", "-", "*"):
            if lt == "bool" or rt == "bool":
                self.error(node, f"cannot apply '{node.op}' to bool")
            node.type = "i64" if ("i64" in (lt, rt)) else "i32"
        elif node.op in ("==", "!="):
            both_int = lt in ("i32", "i64") and rt in ("i32", "i64")
            both_bool = lt == "bool" and rt == "bool"
            if not (both_int or both_bool):
                self.error(node, f"cannot compare {lt} with {rt}")
            node.type = "bool"
        else:
            self.error(node, f"unknown operator '{node.op}'")

        return node.type

    def visit_var(self, node):
        node.decl = self.lookup(node, node.name)
        node.type = node.decl.type_name
        return node.type

    def visit_const(self, node):
        if node.value <= I32_MAX and node.value >= I32_MIN:
            node.type = "i32"
        elif node.value <= I64_MAX and node.value >= I64_MIN:
            node.type = "i64"
        else:
            self.error(node, f"constant {node.value} does not fit in i64")
        return node.type

    def visit_bool(self, node):
        node.type = "bool"
        return node.type

    def visit_block(self, node):
        self.scopes.append({})
        for stmt in node.statements: stmt.accept(self)
        if node.exit: node.exit.accept(self)
        self.scopes.pop()

    def visit_if(self, node):
        cond_type = node.condition.accept(self)
        if cond_type != "bool":
            self.error(node, f"the condition of 'if' must be bool, got {cond_type}")
        
        node.then_block.accept(self)
        if node.else_block:
            node.else_block.accept(self)

    def visit_not(self, node):
        operand_type = node.value.accept(self)
        if operand_type != "bool":
            self.error(node, f"cannot apply '!' to {operand_type}")
        
        node.type = "bool"
        return node.type
