from llvmlite import ir
import llvmlite.binding as llvm

I1 = ir.IntType(1)
I8 = ir.IntType(8)
I8_PTR = ir.PointerType(I8)
I32 = ir.IntType(32)
I64 = ir.IntType(64)

TYPE_MAP = {
    "i32": I32,
    "i64": I64,
    "bool": I1,
}


class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="practices")
        self.module.triple = llvm.get_default_triple()

        main_fn = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.builder = ir.IRBuilder(main_fn.append_basic_block("entry"))

        self.printf = ir.Function(
            self.module,
            ir.FunctionType(I32, [I8_PTR], var_arg=True),
            name="printf",
        )

        # Global format and boolean strings
        self.fmt_int = self._make_global_str("fmt_int", b"Program exit with result %lld\n\0")
        self.fmt_str = self._make_global_str("fmt_str", b"Program exit with result %s\n\0")
        self.str_true = self._make_global_str("str_true", b"true\0")
        self.str_false = self._make_global_str("str_false", b"false\0")

    def _make_global_str(self, name, data):
        arr_ty = ir.ArrayType(I8, len(data))
        gvar = ir.GlobalVariable(self.module, arr_ty, name=name)
        gvar.linkage = "private"
        gvar.global_constant = True
        gvar.initializer = ir.Constant(arr_ty, bytearray(data))
        return gvar

    def coerce(self, value, have, want):
        if have == "i32" and want == "i64":
            return self.builder.sext(value, I64, name="wide")
        return value

    def visit_program(self, node):
        for stmt in node.statements:
            stmt.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        init_val = node.init.accept(self)
        init_val = self.coerce(init_val, node.init.type, node.type_name)

        ptr = self.builder.alloca(TYPE_MAP[node.type_name], name=node.name)
        self.builder.store(init_val, ptr)

        node.ptr = ptr

    def visit_assign(self, node):
        val = node.value.accept(self)
        val = self.coerce(val, node.value.type, node.decl.type_name)
        self.builder.store(val, node.decl.ptr)

    def visit_exit(self, node):
        val = node.value.accept(self)

        if node.value.type == "bool":
            fmt_ptr = self.builder.bitcast(self.fmt_str, I8_PTR)
            true_ptr = self.builder.bitcast(self.str_true, I8_PTR)
            false_ptr = self.builder.bitcast(self.str_false, I8_PTR)
            chosen_str = self.builder.select(val, true_ptr, false_ptr, name="bool_str")
            self.builder.call(self.printf, [fmt_ptr, chosen_str])
        else:
            val = self.coerce(val, node.value.type, "i64")
            fmt_ptr = self.builder.bitcast(self.fmt_int, I8_PTR)
            self.builder.call(self.printf, [fmt_ptr, val])

        self.builder.ret(ir.Constant(I32, 0))

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)

        if node.op in ("+", "-", "*"):
            left = self.coerce(left, node.left.type, node.type)
            right = self.coerce(right, node.right.type, node.type)

            if node.op == "+":
                return self.builder.add(left, right, name="addtmp")
            elif node.op == "-":
                return self.builder.sub(left, right, name="subtmp")
            elif node.op == "*":
                return self.builder.mul(left, right, name="multmp")
        else:
            target_type = "i64" if "i64" in (node.left.type, node.right.type) else node.left.type
            left = self.coerce(left, node.left.type, target_type)
            right = self.coerce(right, node.right.type, target_type)
            return self.builder.icmp_signed(node.op, left, right, name="cmptmp")

    def visit_var(self, node):
        return self.builder.load(node.decl.ptr, name=node.name)

    def visit_const(self, node):
        return ir.Constant(TYPE_MAP[node.type], node.value)

    def visit_bool(self, node):
        return ir.Constant(I1, 1 if node.value else 0)