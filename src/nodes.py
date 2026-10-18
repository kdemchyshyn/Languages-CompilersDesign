class Node:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def dump(self, indent=0):
        raise NotImplementedError()

    def accept(self, visitor):
        raise NotImplementedError()

class ProgramNode(Node):
    def __init__(self, line, col, structs, functions, statements, exit_node):
        super().__init__(line, col)
        self.structs = structs
        self.functions = functions
        self.statements = statements
        self.exit = exit_node

    def dump(self, indent=0):
        print("  " * indent + "Program")
        for struct in self.structs:
            struct.dump(indent + 1)
        for func in self.functions:
            func.dump(indent + 1)
        for stmt in self.statements:
            stmt.dump(indent + 1)
        self.exit.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_program(self)


class FieldDeclNode(Node):
    def __init__(self, line, col, name, type_name, mutable):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable

    def dump(self, indent=0):
        mut_str = "mut" if self.mutable else "const"
        print("  " * indent + f"Member {self.name} {self.type_name} {mut_str}")


class InitListNode(Node):
    def __init__(self, line, col, values):
        super().__init__(line, col)
        self.values = values
        self.type_name = None

    def dump(self, indent=0):
        print("  " * indent + "InitList")
        for val in self.values:
            val.dump(indent + 1)
    

class StructNode(Node):
    def __init__(self, line, col, name, fields, methods=None):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.methods = methods

    def dump(self, indent=0):
        print("  " * indent + f"Struct {self.name}")
        for field in self.fields:
            field.dump(indent + 1)
        if self.methods:
            for method in self.methods:
                method.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_struct(self)


class ParamNode(Node):
    def __init__(self, line, col, name, type_name):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name

    def dump(self, indent=0):
        print("  " * indent + f"Param {self.name} {self.type_name}")


class FunctionNode(Node):
    def __init__(self, line, col, name, return_type, params, body):
        super().__init__(line, col)
        self.name = name
        self.return_type = return_type
        self.params = params
        self.body = body

    def dump(self, indent=0):
        print("  " * indent + f"Function {self.name} -> {self.return_type}")
        for param in self.params:
            param.dump(indent + 1)
        self.body.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_function(self)


class MemberFnNode(Node):
    def __init__(self, line, col, name, return_type, params, body):
        super().__init__(line, col)
        self.name = name
        self.return_type = return_type
        self.params = params
        self.body = body

    def dump(self, indent=0):
        print("  " * indent + f"MemberFn {self.name} -> {self.return_type}")
        for param in self.params:
            param.dump(indent + 1)
        self.body.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_member_fn(self)

class StringNode(Node):
    def __init__(self, line, col, text):
        super().__init__(line, col)
        self.text = text

    def dump(self, indent=0):
        print("  " * indent + f'String "{self.text}"')


class StmtNode(Node): pass

class DeclNode(StmtNode):
    def __init__(self, line, col, name, type_name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init

    def dump(self, indent=0):
        mut_str = "mut" if self.mutable else "const"
        print("  " * indent + f"Decl {self.name} {self.type_name} {mut_str}")
        self.init.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_decl(self)

class AssignNode(StmtNode):
    def __init__(self, line, col, name, fields, value):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.value = value
        self.decl = None
        self.field_indices = []

    def dump(self, indent=0):
        path = ".".join([self.name] + self.fields)
        print("  " * indent + f"Assign {path}")
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

class IfNode(StmtNode):
    def __init__(self, line, col, condition, then_block, else_block):
        super().__init__(line, col)
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

    def dump(self, indent=0):
        print("  " * indent + "If")
        self.condition.dump(indent + 1)
        self.then_block.dump(indent + 1)
        if self.else_block:
            self.else_block.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_if(self)

class WhileNode(StmtNode):
    def __init__(self, line, col, condition, body):
        super().__init__(line, col)
        self.condition = condition
        self.body = body

    def dump(self, indent=0):
        print("  " * indent + "While")
        self.condition.dump(indent + 1)
        self.body.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_while(self)


class PrintNode(StmtNode):
    def __init__(self, line, col, arg, is_string=False):
        super().__init__(line, col)
        self.arg = arg
        self.is_string = is_string

    def dump(self, indent=0):
        print("  " * indent + "Print")
        self.arg.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_print(self)


class ExprNode(Node):
    def __init__(self, line, col):
        super().__init__(line, col)
        self.type = None

class FieldNode(ExprNode):
    def __init__(self, line, col, base_name, fields):
        super().__init__(line, col)
        self.base_name = base_name
        self.fields = fields
        self.decl = None
        self.field_indices = []

    def dump(self, indent=0):
        path = ".".join([self.base_name] + self.fields)
        print("  " * indent + f"Field {path}")

    def accept(self, visitor):
        return visitor.visit_field(self)


class CallNode(ExprNode):
    def __init__(self, line, col, func_name, args):
        super().__init__(line, col)
        self.func_name = func_name
        self.args = args
        self.fn_decl = None
        self.widen_args = []

    def dump(self, indent=0):
        print("  " * indent + f"Call {self.func_name}")
        for arg in self.args:
            arg.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_call(self)


class MemberCallNode(ExprNode):
    def __init__(self, line, col, name, target, args):
        super().__init__(line, col)
        self.name = name
        self.target = target #VarNode or FieldNode
        self.args = args
        self.fn_decl = None
        self.widen_args = []
        self.struct_name = None

    def dump(self, indent=0):
        print("  " * indent + f"MemberCall {self.name}")
        self.target.dump(indent + 1)
        for arg in self.args:
            arg.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_member_call(self)


class ReadNode(ExprNode):
    def __init__(self, line, col):
        super().__init__(line, col)

    def dump(self, indent=0):
        print("  " * indent + "Read")

    def accept(self, visitor):
        return visitor.visit_read(self)


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

class NotNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        print("  " * indent + "Not")
        self.value.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_not(self)

class VarNode(ExprNode):
    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name
        self.decl = None

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

class BoolNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        val_str = "true" if self.value else "false"
        print("  " * indent + f"Bool {val_str}")

    def accept(self, visitor):
        return visitor.visit_bool(self)

class BlockNode(Node):
    def __init__(self, line, col, statements, exit_node):
        super().__init__(line, col)
        self.statements = statements
        self.exit = exit_node

    def dump(self, indent=0):
        print("  " * indent + "Block")
        for stmt in self.statements:
            stmt.dump(indent + 1)
        if self.exit:
            self.exit.dump(indent + 1)

    def accept(self, visitor):
        return visitor.visit_block(self)
