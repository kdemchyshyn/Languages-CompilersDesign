import gc
from pathlib import Path
import sys
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lexer import lex
from parser import Parser
from semantic_checker import SemanticChecker
from optimizer import remove_unused


SOURCE = "i32 top{1}\nif true\n{\n i32 inner{2}\n}\nexit 0\n"


def measure(keep_checker):
    tree = Parser(lex(SOURCE.encode())).parse_program()
    checker = SemanticChecker()
    checker.visit_program(tree)
    block_ref = weakref.ref(tree.statements[1].then_block.statements[0])
    top_ref = weakref.ref(tree.statements[0])
    state = "alive" if keep_checker else "deleted"
    if not keep_checker:
        del checker
    remove_unused(tree)
    print(f"checker {state}, immediately: block freed={block_ref() is None}, "
          f"top-level freed={top_ref() is None}")
    gc.collect()
    print(f"checker {state}, after gc.collect(): block freed={block_ref() is None}, "
          f"top-level freed={top_ref() is None}")


if __name__ == "__main__":
    measure(True)
    measure(False)
