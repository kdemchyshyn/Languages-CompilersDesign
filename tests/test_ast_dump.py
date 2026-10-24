import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nodes import ConstNode, DeclNode, InitListNode


class DeclarationDumpTests(unittest.TestCase):
    def dump(self, node):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            node.dump()
        return output.getvalue()

    def test_scalar_declaration_matches_earlier_format(self):
        init = InitListNode(1, 1, [ConstNode(1, 1, 5)])
        decl = DeclNode(1, 1, "x", "i32", False, init)
        self.assertEqual(self.dump(decl), "Decl x i32 const\n  Const 5\n")
        self.assertIs(decl.init, init)

    def test_nested_initializer_lists_are_preserved(self):
        inner = InitListNode(1, 1, [ConstNode(1, 1, 5)])
        nested = InitListNode(1, 1, [inner, ConstNode(1, 1, 6)])
        init = InitListNode(1, 1, [nested, ConstNode(1, 1, 7)])
        decl = DeclNode(1, 1, "x", "Outer", False, init)
        self.assertEqual(
            self.dump(decl),
            "Decl x Outer const\n  InitList\n    InitList\n"
            "      Const 5\n    Const 6\n  Const 7\n",
        )

    def test_standalone_initializer_list_is_unchanged(self):
        init = InitListNode(1, 1, [ConstNode(1, 1, 5)])
        self.assertEqual(self.dump(init), "InitList\n  Const 5\n")


if __name__ == "__main__":
    unittest.main()
