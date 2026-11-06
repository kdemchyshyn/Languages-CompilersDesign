from nodes import (
    ProgramNode, StructNode, FunctionNode, MemberFnNode, BlockNode, LambdaNode,
    DeclNode, InitListNode, AssignNode, IfNode, WhileNode, ExitNode, BinOpNode,
    NotNode, PrintNode, FieldNode, CallNode, MemberCallNode, ReadNode,
)


def remove_unused(tree, stats=None):
    if stats is None:
        stats = {}
    stats["rounds"] = 0
    stats["removed_decls"] = []
    stats["removed_functions"] = []
    while True:
        stats["rounds"] += 1
        counter = UseCounter()
        counter.visit(tree)
        dead = {id(decl) for decl in counter.decls
                if counter.reads[id(decl)] == 0
                and not getattr(decl, "is_closure", False)}
        pruner = Pruner(dead)
        pruner.visit(tree)
        stats["removed_decls"].extend(pruner.removed)
        if not pruner.removed:
            return tree


def children(node):
    if isinstance(node, ProgramNode):
        return node.structs + node.functions + node.statements + [node.exit]
    if isinstance(node, StructNode):
        return node.methods or []
    if isinstance(node, (FunctionNode, MemberFnNode)):
        return [node.body]
    if isinstance(node, BlockNode):
        return node.statements + ([node.exit] if node.exit is not None else [])
    if isinstance(node, LambdaNode) and node.struct is not None:
        return [node.decl, node.struct]
    if isinstance(node, DeclNode):
        return node.init.values
    if isinstance(node, InitListNode):
        return node.values
    if isinstance(node, (AssignNode, ExitNode, NotNode)):
        return [node.value]
    if isinstance(node, IfNode):
        return [node.condition, node.then_block] + (
            [node.else_block] if node.else_block is not None else [])
    if isinstance(node, WhileNode):
        return [node.condition, node.body]
    if isinstance(node, BinOpNode):
        return [node.left, node.right]
    if isinstance(node, PrintNode):
        return [] if node.is_string else [node.arg]
    if isinstance(node, FieldNode):
        return [node.target] if node.target is not None else []
    if isinstance(node, CallNode):
        return [node.sugar] if node.sugar is not None else node.args
    if isinstance(node, MemberCallNode):
        return [node.target] + node.args
    return []


class Walker:
    def visit(self, node):
        name = type(node).__name__.removesuffix("Node").lower()
        handler = getattr(self, "on_" + name, None)
        if handler is not None:
            return handler(node)
        for child in children(node):
            self.visit(child)


def has_call_or_read(expr):
    return isinstance(expr, (CallNode, MemberCallNode, ReadNode)) or any(
        has_call_or_read(child) for child in children(expr))


class UseCounter(Walker):
    def __init__(self):
        self.reads = {}
        self.decls = []
        self.seen = set()

    def visit(self, node):
        if id(node) in self.seen:
            return
        self.seen.add(id(node))
        return super().visit(node)

    def on_decl(self, node):
        self.decls.append(node)
        self.reads.setdefault(id(node), 0)
        if any(has_call_or_read(value) for value in node.init.values):
            self.reads[id(node)] += 1
        for value in node.init.values:
            self.visit(value)

    def on_var(self, node):
        if node.decl is not None:
            key = id(node.decl)
            self.reads[key] = self.reads.get(key, 0) + 1

    def on_field(self, node):
        self.on_var(node)
        if node.target is not None:
            self.visit(node.target)

    def on_assign(self, node):
        if node.decl is not None and has_call_or_read(node.value):
            self.on_var(node)  # Keep the target of an effectful assignment.
        self.visit(node.value)


class Pruner(Walker):
    def __init__(self, dead):
        self.dead = dead
        self.removed = []

    def on_program(self, node):
        for child in node.structs + node.functions:
            self.visit(child)
        self.on_block(node)

    def on_block(self, node):
        statements = []
        for statement in node.statements:
            if isinstance(statement, DeclNode) and id(statement) in self.dead:
                self.removed.append(statement.name)
                continue
            if (isinstance(statement, AssignNode) and statement.decl is not None
                    and id(statement.decl) in self.dead):
                continue
            self.visit(statement)
            statements.append(statement)
        node.statements = statements
