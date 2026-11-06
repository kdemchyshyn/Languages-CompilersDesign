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
        dead_functions = {name for name, count in counter.calls.items() if count == 0}
        pruner = Pruner(dead, dead_functions)
        pruner.visit(tree)
        stats["removed_decls"].extend(pruner.removed)
        stats["removed_functions"].extend(pruner.removed_functions)
        if not pruner.removed and not pruner.removed_functions:
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


def _call_key(node):
    if isinstance(node, CallNode) and node.sugar is not None:
        node = node.sugar
    if isinstance(node, CallNode) and not getattr(node, "is_this_call", False):
        return ("fn", node.func_name)
    return (node.fn_decl.struct_name, node.fn_decl.name)


def analyze_effects(program):
    """Return effectful function keys without changing the checked tree."""
    bodies = {("fn", function.name): function.body for function in program.functions}
    for struct in program.structs + program.generated_structs:
        for method in struct.methods or []:
            bodies[(struct.name, method.name)] = method.body
    calls = {key: set() for key in bodies}
    effects = set()

    def scan(node, owner):
        if isinstance(node, LambdaNode):
            return  # Its generated call body is analysed separately.
        if isinstance(node, (PrintNode, ReadNode, WhileNode)):
            effects.add(owner)
        # Methods have no info link; checked field writes are the checker's
        # direct mutation seeds, including mutable captures.
        if isinstance(node, AssignNode) and getattr(node, "is_this_field", False):
            effects.add(owner)
        if isinstance(node, (CallNode, MemberCallNode)):
            callee = _call_key(node)
            calls[owner].add(callee)
            if getattr(node.fn_decl, "mutating", False):
                effects.add(callee)
        for child in children(node):
            scan(child, owner)

    for key, body in bodies.items():
        scan(body, key)
    for key in calls:
        pending = list(calls[key])
        seen = set()
        while pending:
            callee = pending.pop()
            if callee == key:
                effects.add(key)
                break
            if callee not in seen:
                seen.add(callee)
                pending.extend(calls[callee])
    while True:
        added = {key for key, callees in calls.items() if callees & effects} - effects
        if not added:
            return effects
        effects.update(added)


def has_effect(expr, effects):
    if isinstance(expr, LambdaNode):
        return False
    if isinstance(expr, ReadNode):
        return True
    if isinstance(expr, (CallNode, MemberCallNode)):
        if _call_key(expr) in effects or getattr(expr.fn_decl, "mutating", False):
            return True
    return any(has_effect(child, effects) for child in children(expr))


class UseCounter(Walker):
    def __init__(self):
        self.reads = {}
        self.calls = {}
        self.decls = []
        self.seen = set()

    def visit(self, node):
        if id(node) in self.seen:
            return
        self.seen.add(id(node))
        return super().visit(node)

    def on_program(self, node):
        self.calls = {function.name: 0 for function in node.functions}
        for child in children(node):
            self.visit(child)

    def on_call(self, node):
        if node.sugar is None and not getattr(node, "is_this_call", False):
            # Self-calls and mutually recursive cycles count, so unused cycles stay.
            self.calls[node.func_name] += 1
        for child in children(node):
            self.visit(child)

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
    def __init__(self, dead, dead_functions):
        self.dead = dead
        self.dead_functions = dead_functions
        self.removed = []
        self.removed_functions = []
        self.lambda_structs = set()

    def on_program(self, node):
        functions = []
        for function in node.functions:
            if function.name in self.dead_functions:
                self.removed_functions.append(function.name)
            else:
                functions.append(function)
        node.functions = functions
        for child in node.structs + node.functions:
            self.visit(child)
        self.on_block(node)
        node.generated_structs = [struct for struct in node.generated_structs
                                  if id(struct) in self.lambda_structs]

    def on_lambda(self, node):
        if node.struct is not None:
            self.lambda_structs.add(id(node.struct))
        for child in children(node):
            self.visit(child)

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
