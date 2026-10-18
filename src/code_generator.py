from llvmlite import ir
import llvmlite.binding as llvm
from nodes import InitListNode, VarNode, FieldNode

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

        self.function = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.entry_block = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry_block)

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

        self.struct_types = {}
        self.struct_field_types = {}
        self.struct_field_names = {}
        self.llvm_functions = {}
        self.current_fn_params = {}

        self.llvm_member_functions = {}
        self.current_this_ptr = None

        self.global_strs = {}
        self.fmt_read = self._get_or_make_global_str(b"%d\0")
        self.fmt_print_i32 = self._get_or_make_global_str(b"%d\n\0")
        self.fmt_print_i64 = self._get_or_make_global_str(b"%lld\n\0")
        self.fmt_print_str = self._get_or_make_global_str(b"%s\n\0")
        
        self.scanf = ir.Function(
            self.module,
            ir.FunctionType(I32, [I8_PTR], var_arg=True),
            name="scanf",
        )

    def _get_or_make_global_str(self, text_bytes):
        if text_bytes in self.global_strs:
            return self.global_strs[text_bytes]
            
        name = f"str_const_{len(self.global_strs)}"
        arr_ty = ir.ArrayType(I8, len(text_bytes))
        gvar = ir.GlobalVariable(self.module, arr_ty, name=name)
        gvar.linkage = "private"
        gvar.global_constant = True
        gvar.initializer = ir.Constant(arr_ty, bytearray(text_bytes))
        self.global_strs[text_bytes] = gvar
        return gvar

    def _make_global_str(self, name, data):
        arr_ty = ir.ArrayType(I8, len(data))
        gvar = ir.GlobalVariable(self.module, arr_ty, name=name)
        gvar.linkage = "private"
        gvar.global_constant = True
        gvar.initializer = ir.Constant(arr_ty, bytearray(data))
        return gvar

    def _alloca_in_entry(self, typ, name):
        current_block = self.builder.block

        self.builder.position_at_start(self.entry_block)
        ptr = self.builder.alloca(typ, name=name)

        self.builder.position_at_end(current_block)
        return ptr

    def coerce(self, value, have, want):
        if have == "i32" and want == "i64":
            return self.builder.sext(value, I64, name="wide")
        return value

    def get_llvm_type(self, type_name):
        if type_name in TYPE_MAP:
            return TYPE_MAP[type_name]
        if type_name in self.struct_types:
            return self.struct_types[type_name]
        raise ValueError(f"Unknown type: {type_name}")

    def visit_program(self, node):
        # Emit named LLVM struct types
        for struct_decl in node.structs:
            llvm_st = self.module.context.get_identified_type(struct_decl.name)
            self.struct_types[struct_decl.name] = llvm_st
            self.struct_field_types[struct_decl.name] = [f.type_name for f in struct_decl.fields]
            self.struct_field_names[struct_decl.name] = [f.name for f in struct_decl.fields]

        for struct_decl in node.structs:
            llvm_st = self.struct_types[struct_decl.name]
            llvm_st.set_body(*[self.get_llvm_type(f.type_name) for f in struct_decl.fields])

        for struct_decl in node.structs:
            this_ptr_type = ir.PointerType(self.struct_types[struct_decl.name])
            for fn in struct_decl.methods:
                param_types = [this_ptr_type] + [self.get_llvm_type(p.type_name) for p in fn.params]
                ret_type = self.get_llvm_type(fn.return_type)
                fn_type = ir.FunctionType(ret_type, param_types)
                llvm_fn = ir.Function(self.module, fn_type, name=f"{struct_decl.name}_{fn.name}")
                self.llvm_member_functions[(struct_decl.name, fn.name)] = llvm_fn

        # Declare all user functions with an IR prefix
        for fn in node.functions:
            param_types = [self.get_llvm_type(p.type_name) for p in fn.params]
            ret_type = self.get_llvm_type(fn.return_type)
            fn_type = ir.FunctionType(ret_type, param_types)
            self.llvm_functions[fn.name] = ir.Function(self.module, fn_type, name=f"_user_{fn.name}")

        for struct_decl in node.structs:
            for fn in struct_decl.methods:
                self.visit_member_fn(fn, struct_decl.name)

        # Generate user function bodies
        for fn in node.functions:
            fn.accept(self)

        # Generate statements for main
        for stmt in node.statements:
            stmt.accept(self)
        node.exit.accept(self)

    def visit_function(self, node):
        saved_func = self.function
        saved_builder = self.builder
        saved_entry = self.entry_block
        saved_params = self.current_fn_params.copy()

        llvm_fn = self.llvm_functions[node.name]
        self.function = llvm_fn
        self.entry_block = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry_block)

        self.current_fn_params = {}
        for p, arg in zip(node.params, llvm_fn.args):
            slot = self._alloca_in_entry(self.get_llvm_type(p.type_name), p.name)
            self.builder.store(arg, slot)
            p.slot = slot
            self.current_fn_params[p.name] = slot

        node.body.accept(self)

        self.function = saved_func
        self.builder = saved_builder
        self.entry_block = saved_entry
        self.current_fn_params = saved_params

    def visit_member_fn(self, node, struct_name):
        saved_func = self.function
        saved_builder = self.builder
        saved_entry = self.entry_block
        saved_params = self.current_fn_params.copy()
        saved_this_ptr = self.current_this_ptr

        llvm_fn = self.llvm_member_functions[(struct_name, node.name)]
        self.function = llvm_fn
        self.entry_block = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry_block)

        # First argument is 'this', do NOT alloca or load, keep it as pointer
        self.current_this_ptr = llvm_fn.args[0]
        self.current_this_ptr.name = "this"

        self.current_fn_params = {}
        for p, arg in zip(node.params, llvm_fn.args[1:]):
            slot = self._alloca_in_entry(self.get_llvm_type(p.type_name), p.name)
            self.builder.store(arg, slot)
            p.slot = slot
            self.current_fn_params[p.name] = slot

        node.body.accept(self)

        self.function = saved_func
        self.builder = saved_builder
        self.entry_block = saved_entry
        self.current_fn_params = saved_params
        self.current_this_ptr = saved_this_ptr

    def eval_init_val(self, init_val, expected_type_name):
        if isinstance(init_val, InitListNode):
            struct_name = init_val.struct_type
            agg = ir.Constant(self.struct_types[struct_name], ir.Undefined)
            field_types = self.struct_field_types[struct_name]
            for i, sub_init in enumerate(init_val.values):
                sub_val = self.eval_init_val(sub_init, field_types[i])
                agg = self.builder.insert_value(agg, sub_val, i)
            return agg
        else:
            val = init_val.accept(self)
            return self.coerce(val, init_val.type, expected_type_name)

    def visit_decl(self, node):
        llvm_type = self.get_llvm_type(node.type_name)
        ptr = self._alloca_in_entry(llvm_type, node.name)

        if getattr(node, 'is_copy_init', False):
            val = node.init.values[0].accept(self)
            val = self.coerce(val, node.init.values[0].type, node.type_name)
            self.builder.store(val, ptr)
        else:
            field_types = self.struct_field_types.get(node.type_name, [node.type_name])
            for i, init_val in enumerate(node.init.values):
                if node.type_name in self.struct_types:
                    zero = ir.Constant(ir.IntType(32), 0)
                    idx = ir.Constant(ir.IntType(32), i)
                    field_ptr = self.builder.gep(ptr, [zero, idx], inbounds=True)
                    val = self.eval_init_val(init_val, field_types[i])
                    self.builder.store(val, field_ptr)
                else:
                    # primitive type
                    val = self.eval_init_val(init_val, node.type_name)
                    self.builder.store(val, ptr)

        node.ptr = ptr

    def visit_assign(self, node):
        if getattr(node, 'is_this_field', False):
            base_ptr = self.current_this_ptr
        else:
            base_ptr = getattr(node.decl, 'ptr', None)
            if base_ptr is None:
                base_ptr = self.current_fn_params[node.name]

        if getattr(node, 'field_indices', []):
            ptr = self._gep_chain(base_ptr, node.field_indices)
        else:
            ptr = base_ptr

        val = node.value.accept(self)
        
        # Determine coercion based on pointer type if RHS is i32
        if node.value.type == "i32" and ptr.type.pointee == I64:
            val = self.builder.sext(val, I64, name="wide")
            
        self.builder.store(val, ptr)

    def visit_exit(self, node):
        val = node.value.accept(self)

        # Handle exit inside a user function
        if self.function.name != "main":
            if node.value.type == "i32" and self.function.return_value.type == I64:
                val = self.builder.sext(val, I64)
            self.builder.ret(val)
            return

        # Handle exit at top level (main)
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
        if getattr(node, 'is_this_field', False):
            ptr = self._gep_chain(self.current_this_ptr, [node.field_index])
            return self.builder.load(ptr, name=node.name)

        ptr = getattr(node.decl, 'ptr', None)
        if ptr is None:
            # Fallback for parameters which populate current_fn_params
            ptr = self.current_fn_params[node.name]
        return self.builder.load(ptr, name=node.name)

    def visit_const(self, node):
        return ir.Constant(TYPE_MAP[node.type], node.value)

    def visit_bool(self, node):
        return ir.Constant(I1, 1 if node.value else 0)

    def visit_block(self, node):
        for stmt in node.statements:
            stmt.accept(self)
        if node.exit:
            node.exit.accept(self)

    def visit_if(self, node):
        cond = node.condition.accept(self)

        then_bb = self.function.append_basic_block("then")
        else_bb = self.function.append_basic_block("else") if node.else_block else None
        merge_bb = self.function.append_basic_block("merge")

        self.builder.cbranch(cond, then_bb, else_bb or merge_bb)

        self.builder.position_at_end(then_bb)
        node.then_block.accept(self)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)

        if node.else_block:
            self.builder.position_at_end(else_bb)
            node.else_block.accept(self)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_bb)

        self.builder.position_at_end(merge_bb)

    def visit_not(self, node):
        val = node.value.accept(self)
        return self.builder.not_(val, name="nottmp")

    def visit_while(self, node):
        cond_bb = self.function.append_basic_block("while.cond")
        body_bb = self.function.append_basic_block("while.body")
        end_bb = self.function.append_basic_block("while.end")

        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        cond_val = node.condition.accept(self)        
        self.builder.cbranch(cond_val, body_bb, end_bb)

        self.builder.position_at_end(body_bb)
        node.body.accept(self)

        if not self.builder.block.is_terminated:
            self.builder.branch(cond_bb)

        self.builder.position_at_end(end_bb)

    def _gep_chain(self, base_slot, field_indices):
        ptr = base_slot
        zero = ir.Constant(I32, 0)
        for idx in field_indices:
            ptr = self.builder.gep(
                ptr, [zero, ir.Constant(I32, idx)], inbounds=True
            )
        return ptr

    def visit_field(self, node):
        if getattr(node, 'is_this_field', False):
            base_ptr = self.current_this_ptr
            ptr = self._gep_chain(base_ptr, node.field_indices)
            return self.builder.load(ptr)
            
        if getattr(node, 'target', None) is not None:
            # Field of a call result!
            agg_val = node.target.accept(self)
            for idx in node.field_indices:
                agg_val = self.builder.extract_value(agg_val, idx)
            return agg_val
            
        else:
            base_ptr = getattr(node.decl, 'ptr', None)
            if base_ptr is None:
                base_ptr = self.current_fn_params[node.base_name]
            ptr = self._gep_chain(base_ptr, node.field_indices)
            return self.builder.load(ptr)

    def visit_call(self, node):
        arg_vals = []
        for i, arg in enumerate(node.args):
            val = arg.accept(self)
            if node.widen_args[i]:
                val = self.builder.sext(val, I64)
            arg_vals.append(val)

        if getattr(node, 'is_this_call', False):
            struct_name = node.fn_decl.struct_name
            return self.builder.call(self.llvm_member_functions[(struct_name, node.func_name)], [self.current_this_ptr] + arg_vals)
            
        return self.builder.call(self.llvm_functions[node.func_name], arg_vals)

    def visit_member_call(self, node):
        from nodes import CallNode, MemberCallNode
        
        is_call_result = isinstance(node.target, (CallNode, MemberCallNode)) or \
                         (isinstance(node.target, FieldNode) and getattr(node.target, 'target', None) is not None)
                         
        if is_call_result:
            # Result of a call (or field on a call result). Evaluate to get the aggregate value.
            val = node.target.accept(self)
            
            # Allocate a temporary slot and store the value, then pass the slot's address as 'this'
            tmp_ptr = self._alloca_in_entry(self.struct_types[node.struct_name], "chain.tmp")
            self.builder.store(val, tmp_ptr)
            this_arg = tmp_ptr
            
        elif isinstance(node.target, VarNode):
            if getattr(node.target, 'is_this_field', False):
                this_arg = self._gep_chain(self.current_this_ptr, [node.target.field_index])
            else:
                this_arg = getattr(node.target.decl, 'ptr', None)
                if this_arg is None:
                    this_arg = self.current_fn_params[node.target.name]
                    
        elif isinstance(node.target, FieldNode):
            if getattr(node.target, 'is_this_field', False):
                base_ptr = self.current_this_ptr
            else:
                base_ptr = getattr(node.target.decl, 'ptr', None)
                if base_ptr is None:
                    base_ptr = self.current_fn_params[node.target.base_name]
            this_arg = self._gep_chain(base_ptr, node.target.field_indices)

        arg_vals = []
        for i, arg in enumerate(node.args):
            val = arg.accept(self)
            if node.widen_args[i]:
                val = self.builder.sext(val, I64)
            arg_vals.append(val)

        return self.builder.call(self.llvm_member_functions[(node.struct_name, node.name)], [this_arg] + arg_vals)

    def visit_read(self, node):
        slot = self._alloca_in_entry(I32, "read")
        fmt_ptr = self.builder.bitcast(self.fmt_read, I8_PTR)
        self.builder.call(self.scanf, [fmt_ptr, slot])
        return self.builder.load(slot, name="read.val")

    def visit_print(self, node):
        if node.is_string:
            str_const = self._get_or_make_global_str(node.arg.text.encode() + b"\0")
            fmt_ptr = self.builder.bitcast(self.fmt_print_str, I8_PTR)
            str_ptr = self.builder.bitcast(str_const, I8_PTR)
            self.builder.call(self.printf, [fmt_ptr, str_ptr])
        elif node.arg.type == "i32":
            val = node.arg.accept(self)
            fmt_ptr = self.builder.bitcast(self.fmt_print_i32, I8_PTR)
            self.builder.call(self.printf, [fmt_ptr, val])
        elif node.arg.type == "i64":
            val = node.arg.accept(self)
            fmt_ptr = self.builder.bitcast(self.fmt_print_i64, I8_PTR)
            self.builder.call(self.printf, [fmt_ptr, val])
        elif node.arg.type == "bool":
            val = node.arg.accept(self)
            true_ptr = self.builder.bitcast(self.str_true, I8_PTR)
            false_ptr = self.builder.bitcast(self.str_false, I8_PTR)
            chosen = self.builder.select(val, true_ptr, false_ptr)
            fmt_ptr = self.builder.bitcast(self.fmt_print_str, I8_PTR)
            self.builder.call(self.printf, [fmt_ptr, chosen])
        elif node.arg.type in self.struct_types:
            struct_name = node.arg.type
            if isinstance(node.arg, VarNode):
                if getattr(node.arg, 'is_this_field', False):
                    struct_ptr = self._gep_chain(self.current_this_ptr, [node.arg.field_index])
                else:
                    struct_ptr = getattr(node.arg.decl, 'ptr', None)
                    if struct_ptr is None:
                        struct_ptr = self.current_fn_params[node.arg.name]
            elif isinstance(node.arg, FieldNode):
                if getattr(node.arg, 'target', None) is not None:
                    val = node.arg.accept(self)
                    struct_ptr = self._alloca_in_entry(self.struct_types[struct_name], "print.tmp")
                    self.builder.store(val, struct_ptr)
                else:
                    if getattr(node.arg, 'is_this_field', False):
                        base_ptr = self.current_this_ptr
                    else:
                        base_ptr = getattr(node.arg.decl, 'ptr', None)
                        if base_ptr is None:
                            base_ptr = self.current_fn_params[node.arg.base_name]
                    struct_ptr = self._gep_chain(base_ptr, node.arg.field_indices)
            else:
                val = node.arg.accept(self)
                struct_ptr = self._alloca_in_entry(self.struct_types[struct_name], "print.tmp")
                self.builder.store(val, struct_ptr)
            
            self._emit_print_struct(struct_name, struct_ptr, is_top_level=True)

    def _emit_print_struct(self, struct_name, struct_ptr, is_top_level=True):
        open_str = self._get_or_make_global_str(f"{struct_name}{{".encode() + b"\0")
        open_ptr = self.builder.bitcast(open_str, I8_PTR)
        self.builder.call(self.printf, [open_ptr])

        field_types = self.struct_field_types[struct_name]
        field_names = self.struct_field_names[struct_name]
        
        for i, (field_name, field_type) in enumerate(zip(field_names, field_types)):
            prefix = f"{field_name}: " if i == 0 else f", {field_name}: "
            field_ptr = self.builder.gep(struct_ptr, [ir.Constant(I32, 0), ir.Constant(I32, i)], inbounds=True)
            
            if field_type in self.struct_types:
                prefix_str = self._get_or_make_global_str(prefix.encode() + b"\0")
                self.builder.call(self.printf, [self.builder.bitcast(prefix_str, I8_PTR)])
                self._emit_print_struct(field_type, field_ptr, is_top_level=False)
            else:
                field_val = self.builder.load(field_ptr)
                if field_type == "i32":
                    fmt = self._get_or_make_global_str((prefix + "%d").encode() + b"\0")
                    self.builder.call(self.printf, [self.builder.bitcast(fmt, I8_PTR), field_val])
                elif field_type == "i64":
                    fmt = self._get_or_make_global_str((prefix + "%lld").encode() + b"\0")
                    self.builder.call(self.printf, [self.builder.bitcast(fmt, I8_PTR), field_val])
                elif field_type == "bool":
                    fmt = self._get_or_make_global_str((prefix + "%s").encode() + b"\0")
                    true_ptr = self.builder.bitcast(self.str_true, I8_PTR)
                    false_ptr = self.builder.bitcast(self.str_false, I8_PTR)
                    chosen = self.builder.select(field_val, true_ptr, false_ptr)
                    self.builder.call(self.printf, [self.builder.bitcast(fmt, I8_PTR), chosen])
                    
        close_str = self._get_or_make_global_str(b"}\n\0" if is_top_level else b"}\0")
        self.builder.call(self.printf, [self.builder.bitcast(close_str, I8_PTR)])
