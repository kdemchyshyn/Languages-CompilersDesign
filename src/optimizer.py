from nodes import (
    ProgramNode, StructNode, FunctionNode, MemberFnNode, BlockNode, LambdaNode,
    DeclNode, InitListNode, AssignNode, IfNode, WhileNode, ExitNode, BinOpNode,
    NotNode, PrintNode, FieldNode, CallNode, MemberCallNode,
)


def remove_unused(tree, stats=None):
    if stats is not None:
        stats["rounds"] = 0
        stats["removed_decls"] = []
        stats["removed_functions"] = []
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
