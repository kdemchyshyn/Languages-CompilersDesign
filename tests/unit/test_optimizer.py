from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lexer import lex
from parser import Parser
from semantic_checker import SemanticChecker
from code_generator import CodeGen
from llvmlite import binding
from nodes import AssignNode, ConstNode, FieldNode, VarNode
import optimizer
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
        self.assertEqual([node.name for node in tree.statements], ["z"])
        self.assertIs(tree.exit.value.decl, tree.statements[0])

    def test_warmup_shadow(self):
        tree = checked("i32 mut r{0}\ni32 x{1}\nif true\n{\n"
                       " i32 x{10}\n r := x\n}\nexit r\n")
        r, outer_x, branch = tree.statements
        inner_x, assignment = branch.then_block.statements
        stats = {}
        self.assertIs(remove_unused(tree, stats), tree)
        self.assertEqual(stats["removed_functions"], [])
        self.assertEqual((stats["rounds"], stats["removed_decls"]), (2, ["x"]))
        self.assertEqual(tree.statements, [r, branch])
        self.assertEqual(branch.then_block.statements, [inner_x, assignment])
        self.assertIs(assignment.decl, r)
        self.assertIs(assignment.value.decl, inner_x)
        self.assertIsNot(inner_x, outer_x)

    def test_unread_assignment_is_removed_and_tree_is_codegen_ready(self):
        tree = checked("i32 mut y{0}\ny := 5\nexit 0\n")
        remove_unused(tree)
        self.assertEqual(tree.statements, [])
        codegen = CodeGen()
        tree.accept(codegen)
        binding.parse_assembly(str(codegen.module)).verify()

    def test_unread_field_assignment_is_removed_and_tree_is_codegen_ready(self):
        tree = checked("""struct WriteOnly
{
    i32 mut x
}
WriteOnly mut p{0}
p.x := 5
exit 0
""")
        remove_unused(tree)
        self.assertEqual(tree.statements, [])
        self.assertEqual(tree.structs[0].fields[0].name, "x")
        codegen = CodeGen()
        tree.accept(codegen)
        binding.parse_assembly(str(codegen.module)).verify()

    def test_unread_parameter_stays(self):
        tree = checked("fn f := (i32 unused) -> i32\n{\n"
                       " i32 dead{2}\n exit 1\n}\nexit f(0)\n")
        function = tree.functions[0]
        parameter = function.params[0]
        remove_unused(tree)
        self.assertEqual(tree.functions, [function])
        self.assertEqual(function.params, [parameter])
        self.assertEqual(function.body.statements, [])

    def test_self_increment_is_a_read(self):
        tree = checked("i32 mut k{0}\nk := k + 1\nexit 0\n")
        before = tree.statements[:]
        remove_unused(tree)
        self.assertEqual(tree.statements, before)

    def test_reachable_lambda_capture_keeps_variable(self):
        tree = checked("i32 k{7}\nfn f := [k]() -> i32\n{\n"
                       " exit k\n}\nexit f()\n")
        k, closure = tree.statements
        remove_unused(tree)
        self.assertEqual(tree.statements, [k, closure])
        self.assertIs(closure.decl.init.values[0].decl, k)
        self.assertIsNone(closure.body.exit.value.decl)

    def test_callable_sugar_keeps_object(self):
        tree = checked("""struct Callable
{
    i32 value
    fn call := (i32 v) -> i32
    {
        exit v
    }
}
Callable c{0}
exit c(5)
""")
        c = tree.statements[0]
        remove_unused(tree)
        self.assertEqual(tree.statements, [c])
        self.assertIs(tree.exit.value.sugar.target.decl, c)

    def test_call_initializer_stays(self):
        tree = checked("fn f := () -> i32\n{\n exit 1\n}\n"
                       "i32 unused{f()}\nexit 0\n")
        declaration = tree.statements[0]
        remove_unused(tree)
        self.assertEqual(tree.statements, [declaration])

    def test_read_initializer_stays(self):
        tree = checked("i32 unused{read()}\nexit 0\n")
        declaration = tree.statements[0]
        remove_unused(tree)
        self.assertEqual(tree.statements, [declaration])

    def test_effectful_assignment_keeps_target(self):
        for value in ("read()", "f()"):
            with self.subTest(value=value):
                tree = checked("fn f := () -> i32\n{\n exit 1\n}\n"
                               f"i32 mut y{{0}}\ny := {value}\nexit 0\n")
                before = tree.statements[:]
                remove_unused(tree)
                self.assertEqual(tree.statements, before)

    def test_nested_initializer_and_member_call_keep_effects(self):
        tree = checked("""struct Inner
{
    i32 value
    fn get := () -> i32
    {
        exit value
    }
}
struct Outer
{
    Inner inner
}
Inner object{0}
Outer unused{{object.get()}}
exit 0
""")
        before = tree.statements[:]
        remove_unused(tree)
        self.assertEqual(tree.statements, before)

    def test_field_read_and_call_target_are_visited(self):
        tree = checked("""struct Point
{
    i32 x
}
fn point := () -> Point
{
    Point result{3}
    exit result
}
Point p{4}
print(p.x)
i32 unused{point().x}
exit 0
""")
        before = tree.statements[:]
        remove_unused(tree)
        self.assertEqual(tree.statements, before)

    def test_empty_if_else_and_while_blocks_stay(self):
        tree = checked("if true\n{\n i32 a{1}\n}\nelse\n{\n"
                       " i32 b{2}\n}\nwhile false\n{\n i32 c{3}\n}\nexit 0\n")
        branch, loop = tree.statements
        blocks = [branch.then_block, branch.else_block, loop.body]
        remove_unused(tree)
        self.assertEqual(tree.statements, [branch, loop])
        self.assertEqual([block.statements for block in blocks], [[], [], []])
        self.assertIs(branch.then_block, blocks[0])
        self.assertIs(branch.else_block, blocks[1])
        self.assertIs(loop.body, blocks[2])

    def test_member_and_shared_lambda_bodies_are_pruned(self):
        tree = checked("""struct Counter
{
    i32 mut value
    fn next := () -> i32
    {
        i32 method_dead{1}
        value := read()
        exit value
    }
}
i32 k{7}
fn unused := [k]() -> i32
{
    i32 lambda_dead{2}
    exit k
}
exit 0
""")
        k, closure = tree.statements
        body = closure.body
        generated_body = tree.generated_structs[0].methods[0].body
        assignment = tree.structs[0].methods[0].body.statements[1]
        self.assertIsNone(assignment.decl)
        self.assertIs(body, generated_body)
        remove_unused(tree)
        self.assertEqual(tree.statements, [k, closure])
        self.assertEqual(body.statements, [])
        self.assertIs(closure.body, generated_body)
        self.assertEqual(tree.structs[0].methods[0].body.statements, [assignment])

    def test_counter_counts_shared_nodes_once_and_guards_missing_decl(self):
        tree = checked("i32 k{7}\nfn f := [k]() -> i32\n{\n"
                       " i32 local{1}\n print(local)\n exit k\n}\nexit f()\n")
        k, closure = tree.statements
        local = closure.body.statements[0]
        # Expose the generated method by a second path to the same checked nodes.
        tree.structs.append(closure.struct)
        self.assertIsNotNone(getattr(optimizer, "UseCounter", None))
        counter = optimizer.UseCounter()
        counter.visit(tree)
        self.assertEqual(counter.reads[id(k)], 1)
        self.assertEqual(counter.reads[id(closure.decl)], 1)
        self.assertEqual(counter.reads[id(local)], 1)
        self.assertNotIn(id(None), counter.reads)

    def test_unused_function_chain(self):
        tree = checked("""fn twice := (i32 a) -> i32
{
    i32 r{a + a}
    exit r
}
fn helper := (i32 a) -> i32
{
    exit twice(a)
}
fn unused := () -> i32
{
    exit helper(1)
}
exit twice(2)
""")
        stats = {}
        remove_unused(tree, stats)
        self.assertEqual(stats["removed_functions"], ["unused", "helper"])
        self.assertEqual(stats["rounds"], 3)
        self.assertEqual(stats["removed_decls"], [])
        self.assertEqual([fn.name for fn in tree.functions], ["twice"])

    def test_mutually_recursive_unused_functions_stay(self):
        tree = checked("fn first := () -> i32\n{\n exit second()\n}\n"
                       "fn second := () -> i32\n{\n exit first()\n}\nexit 0\n")
        before = tree.functions[:]
        stats = {}
        remove_unused(tree, stats)
        self.assertEqual(tree.functions, before)
        self.assertEqual(stats["removed_functions"], [])
        self.assertEqual(stats["rounds"], 1)

    def test_self_recursive_unused_function_stays(self):
        tree = checked("fn recurse := () -> i32\n{\n exit recurse()\n}\nexit 0\n")
        function = tree.functions[0]
        stats = {}
        remove_unused(tree, stats)
        self.assertEqual(tree.functions, [function])
        self.assertEqual(stats["removed_functions"], [])
        self.assertEqual(stats["rounds"], 1)

    def test_global_call_from_member_function_keeps_function(self):
        tree = checked("""struct Object
{
    i32 value
    fn get := () -> i32
    {
        exit global()
    }
}
fn global := () -> i32
{
    exit 1
}
exit 0
""")
        function = tree.functions[0]
        method = tree.structs[0].methods[0]
        remove_unused(tree)
        self.assertEqual(tree.functions, [function])
        self.assertEqual(tree.structs[0].methods, [method])

    def test_global_call_from_lambda_body_keeps_function(self):
        tree = checked("fn global := () -> i32\n{\n exit 1\n}\n"
                       "fn f := []() -> i32\n{\n exit global()\n}\nexit f()\n")
        function = tree.functions[0]
        closure = tree.statements[0]
        remove_unused(tree)
        self.assertEqual(tree.functions, [function])
        self.assertEqual(tree.statements, [closure])
        self.assertEqual(tree.generated_structs, [closure.struct])

    def test_this_and_callable_calls_are_not_global_calls(self):
        tree = checked("""struct Object
{
    i32 value
    fn helper := () -> i32
    {
        exit value
    }
    fn call := (i32 v) -> i32
    {
        exit helper()
    }
}
fn helper := () -> i32
{
    exit 9
}
Object c{0}
exit c(5)
""")
        methods = tree.structs[0].methods[:]
        c = tree.statements[0]
        counter = optimizer.UseCounter()
        counter.visit(tree)
        self.assertEqual(getattr(counter, "calls", None), {"helper": 0})
        remove_unused(tree)
        self.assertEqual(tree.functions, [])
        self.assertEqual(tree.structs[0].methods, methods)
        self.assertEqual(tree.statements, [c])

    def test_lambdas_in_removed_function_are_not_emitted(self):
        source = """fn leaf := () -> i32
{
    exit 7
}
fn unused := () -> i32
{
    fn doomed := []() -> i32
    {
        fn nested_doomed := []() -> i32
        {
            exit leaf()
        }
        exit nested_doomed()
    }
    exit doomed()
}
fn keep := []() -> i32
{
    fn nested_keep := []() -> i32
    {
        exit 3
    }
    exit nested_keep()
}
exit keep()
"""
        tree = checked(source)
        keep = tree.statements[0]
        nested_keep = keep.body.statements[0]
        stats = {}
        remove_unused(tree, stats)
        self.assertEqual(tree.functions, [])
        self.assertEqual(stats["removed_functions"], ["unused", "leaf"])
        self.assertEqual(stats["rounds"], 3)
        self.assertEqual(tree.generated_structs, [keep.struct, nested_keep.struct])

        compiler = Path(__file__).resolve().parents[2] / "src/compiler.py"
        with tempfile.TemporaryDirectory(prefix="practice9-lambda-") as temp:
            input_path = Path(temp) / "program.txt"
            output_path = Path(temp) / "program.ll"
            input_path.write_text(source)
            compiled = subprocess.run(
                [sys.executable, str(compiler), "--remove-unused",
                 str(input_path), str(output_path)], capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            self.assertEqual((compiled.stdout, compiled.stderr), (b"", b""))
            result = subprocess.run(["lli", str(output_path)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"Program exit with result 3\n")
            self.assertEqual(result.stderr, b"")

    def test_effect_spec_chain_and_arguments(self):
        tree = checked("""fn square := (i32 a) -> i32
{
    i32 r{a * a}
    exit r
}
fn quiet := (i32 a) -> i32
{
    exit square(a)
}
fn chain := (i32 a) -> i32
{
    exit relay(a)
}
fn relay := (i32 a) -> i32
{
    exit loud(a)
}
fn loud := (i32 a) -> i32
{
    print(a)
    exit a
}
i32 a{square(3)}
i32 b{quiet(4)}
i32 c{loud(5)}
i32 d{quiet(loud(1))}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("fn", "loud"), ("fn", "relay"), ("fn", "chain")})
        self.assertEqual([optimizer.has_effect(decl.init.values[0], effects)
                          for decl in tree.statements], [False, False, True, True])

    def test_effect_mutating_and_pure_members(self):
        tree = checked("""struct Counter
{
    i32 mut n
    fn bump := () -> i32
    {
        n := n + 1
        exit n
    }
    fn peek := () -> i32
    {
        exit n
    }
    fn uncalled_bump := () -> i32
    {
        n := n + 2
        exit n
    }
}
Counter mut c{0}
i32 b{c.bump()}
i32 p{c.peek()}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("Counter", "bump"), ("Counter", "uncalled_bump")})
        bump = tree.statements[1].init.values[0]
        peek = tree.statements[2].init.values[0]
        self.assertTrue(optimizer.has_effect(bump, effects))
        self.assertTrue(optimizer.has_effect(bump, set()))  # The call-site mutation flag.
        self.assertFalse(optimizer.has_effect(peek, effects))

    def test_effect_this_calls(self):
        tree = checked("""struct Reporter
{
    i32 value
    fn loud := () -> i32
    {
        print(value)
        exit value
    }
    fn relay := () -> i32
    {
        exit loud()
    }
}
Reporter r{1}
exit r.relay()
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("Reporter", "loud"), ("Reporter", "relay")})
        self.assertTrue(optimizer.has_effect(tree.exit.value, effects))

    def test_effect_while(self):
        tree = checked("fn loop := () -> i32\n{\n while false\n {\n  i32 dead{0}\n }\n"
                       " exit 0\n}\ni32 unused{loop()}\nexit 0\n")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("fn", "loop")})
        self.assertTrue(optimizer.has_effect(tree.statements[0].init.values[0], effects))

    def test_effect_recursion(self):
        tree = checked("""fn recurse := () -> i32
{
    exit recurse()
}
fn first := () -> i32
{
    exit second()
}
fn second := () -> i32
{
    exit first()
}
fn caller := () -> i32
{
    exit first()
}
fn independent := () -> i32
{
    exit 0
}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("fn", "recurse"), ("fn", "first"),
                                   ("fn", "second"), ("fn", "caller")})

    def test_effect_member_recursion(self):
        tree = checked("""struct Loop
{
    i32 value
    fn first := () -> i32
    {
        exit second()
    }
    fn second := () -> i32
    {
        exit first()
    }
}
exit 0
""")
        self.assertEqual(optimizer.analyze_effects(tree),
                         {("Loop", "first"), ("Loop", "second")})

    def test_effect_printing_and_pure_lambdas(self):
        tree = checked("""fn noisy := [](i32 a) -> i32
{
    print(a)
    exit a
}
fn quiet := [](i32 a) -> i32
{
    exit a
}
i32 x{noisy(1)}
i32 y{quiet(2)}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("lambda.noisy", "call")})
        self.assertTrue(optimizer.has_effect(tree.statements[2].init.values[0], effects))
        self.assertFalse(optimizer.has_effect(tree.statements[3].init.values[0], effects))

    def test_effect_mutating_callable(self):
        tree = checked("i32 n{0}\nfn counter := [mut n]() -> i32\n{\n"
                       " n := n + 1\n exit n\n}\ni32 unused{counter()}\nexit 0\n")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("lambda.counter", "call")})
        call = tree.statements[2].init.values[0]
        self.assertTrue(optimizer.has_effect(call, effects))
        self.assertTrue(optimizer.has_effect(call, set()))

    def test_effect_nested_lambda_is_separate(self):
        tree = checked("fn enclosing := () -> i32\n{\n"
                       " fn nested := []() -> i32\n {\n  print(1)\n  exit 0\n }\n"
                       " exit 0\n}\nexit 0\n")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("lambda.nested", "call")})
        self.assertFalse(optimizer.has_effect(tree.functions[0].body.statements[0], effects))

    def test_effect_read_and_nested_initializer(self):
        tree = checked("""struct Box
{
    i32 value
}
struct Outer
{
    Box box
}
fn input := () -> i32
{
    i32 n{read()}
    exit n
}
fn caller := () -> i32
{
    exit input()
}
Outer unused{{read()}}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("fn", "input"), ("fn", "caller")})
        self.assertTrue(optimizer.has_effect(tree.statements[0].init, effects))

    def test_effect_call_target(self):
        tree = checked("""struct Box
{
    i32 value
    fn peek := () -> i32
    {
        exit value
    }
}
fn make := () -> Box
{
    print(1)
    Box result{2}
    exit result
}
i32 unused{make().peek()}
exit 0
""")
        effects = optimizer.analyze_effects(tree)
        self.assertEqual(effects, {("fn", "make")})
        self.assertTrue(optimizer.has_effect(tree.statements[0].init.values[0], effects))


if __name__ == "__main__":
    unittest.main()
