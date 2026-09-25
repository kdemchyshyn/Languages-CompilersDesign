class Node:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def dump(self, indent=0):
        raise NotImplementedError()

    def accept(self, visitor):
        raise NotImplementedError()

class ProgramNode(Node):
    def __init__(self, line, col, statements, exit_node):
        super().__init__(line, col)
        self.statements = statements
        self.exit = exit_node

    def dump(self, indent=0):
        print("  " * indent + "Program")
        for stmt in self.statements:
            stmt.dump(indent + 1)
        self.exit.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_program(self)

class StmtNode(Node): pass

class DeclNode(StmtNode):
    def __init__(self, line, col, name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.mutable = mutable
        self.init = init

    def dump(self, indent=0):
        mut_str = "mut" if self.mutable else "const"
        print("  " * indent + f"Decl {self.name} {mut_str}")
        self.init.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_decl(self)

class AssignNode(StmtNode):
    def __init__(self, line, col, name, value):
        super().__init__(line, col)
        self.name = name
        self.value = value

    def dump(self, indent=0):
        print("  " * indent + f"Assign {self.name}")
        self.value.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_assign(self)

class ExitNode(Node):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        print("  " * indent + "Exit")
        self.value.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_exit(self)

class ExprNode(Node): pass

class BinOpNode(ExprNode):
    def __init__(self, line, col, op, left, right):
        super().__init__(line, col)
        self.op = op
        self.left = left
        self.right = right

    def dump(self, indent=0):
        print("  " * indent + f"BinOp {self.op}")
        self.left.dump(indent + 1)
        self.right.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_binop(self)

class VarNode(ExprNode):
    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name

    def dump(self, indent=0):
        print("  " * indent + f"Var {self.name}")

    def accept(self, visitor):
        return visitor.visit_var(self)

class ConstNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        print("  " * indent + f"Const {self.value}")

    def accept(self, visitor):
        return visitor.visit_const(self)