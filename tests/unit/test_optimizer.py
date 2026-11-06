from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lexer import lex
from parser import Parser
from semantic_checker import SemanticChecker
from nodes import AssignNode, ConstNode, FieldNode, VarNode
from optimizer import children, remove_unused, Walker


def checked(src: str):
    tree = Parser(lex(src.encode())).parse_program()
    SemanticChecker().visit_program(tree)
    return tree


class OptimizerTests(unittest.TestCase):
    def test_children_checked_sugar_nested_init_and_capture(self):
        tree = checked("""struct Box
{
    i32 value
}
struct Pair
{
    Box box
}
struct Callable
{
    i32 value
    fn call := (i32 arg) -> i32
    {
        exit arg
    }
}
i32 seed{7}
Pair p{{seed}}
Callable c{0}
fn add := [seed](i32 v) -> i32
{
    i32 result{seed + v}
    exit result
}
exit c(add(seed))
""")
        names = []

        def collect(node):
            if isinstance(node, VarNode):
                names.append(node.name)
            for child in children(node):
                collect(child)

        collect(tree)
        # Include capture initializers and callable targets, each exactly once.
        self.assertEqual(names, ["arg", "seed", "seed", "seed", "v", "result",
                                 "c", "add", "seed"])

    def test_walker_dispatch(self):
        seen = []

        class Recorder(Walker):
            def on_decl(self, node):
                seen.append("decl")
                for child in children(node):
                    self.visit(child)

            def on_var(self, node):
                seen.append("var")

            def on_field(self, node):
                seen.append("field")

            def on_assign(self, node):
                seen.append("assign")

        tree = checked("i32 x{1}\ni32 y{x}\nexit y\n")
        walker = Recorder()
        walker.visit(tree)  # Program, Const and Exit use the fallback traversal.
        walker.visit(FieldNode(1, 1, "p", ["x"], 1, 2))
        walker.visit(AssignNode(1, 1, "x", [], ConstNode(1, 1, 2)))
        self.assertEqual(seen, ["decl", "decl", "var", "var", "field", "assign"])

    def test_warmup_chain(self):
        tree = checked("i32 x{10}\ni32 y{x}\ni32 z{15}\nexit z\n")
        stats = {}
        self.assertIs(remove_unused(tree, stats), tree)
        self.assertEqual(stats["removed_functions"], [])
        self.assertEqual((stats["rounds"], stats["removed_decls"]), (3, ["y", "x"]))

    def test_warmup_shadow(self):
        tree = checked("i32 mut r{0}\ni32 x{1}\nif true\n{\n"
                       " i32 x{10}\n r := x\n}\nexit r\n")
        stats = {}
        self.assertIs(remove_unused(tree, stats), tree)
        self.assertEqual(stats["removed_functions"], [])
        self.assertEqual((stats["rounds"], stats["removed_decls"]), (2, ["x"]))


if __name__ == "__main__":
    unittest.main()
