from errors import CompileError
from nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode, BoolNode,
    BlockNode, IfNode, NotNode, WhileNode,
    InitListNode, FieldNode, CallNode, 
    StructNode, FunctionNode, ParamNode,
    MemberFnNode, MemberCallNode
)

I32_MAX = 2147483647
I32_MIN = -2147483648
I64_MAX = 9223372036854775807
I64_MIN = -9223372036854775808

class MemberFnInfo:
    def __init__(self, name, struct_name, params, return_type, node):
        self.name = name
        self.struct_name = struct_name
        self.params = params
        self.return_type = return_type
        self.node = node
        self.mutating = False
        self.this_calls = set()


class FieldInfo:
    def __init__(self, type_name, is_mut, index):
        self.type_name = type_name
        self.is_mut = is_mut
        self.index = index


class StructInfo:
    def __init__(self, name, fields_dict, is_deeply_mut):
        self.name = name
        self.fields = fields_dict  # name -> FieldInfo
        self.is_deeply_mut = is_deeply_mut
        self.methods = {}  # name -> MemberFnInfo


class FnInfo:
    def __init__(self, name, params, return_type):
        self.name = name
        self.params = params  # list of ParamNode
        self.return_type = return_type

class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]  # name -> DeclNode
        self.structs = {}   # dict[str, StructInfo]
        self.functions = {} # dict[str, FnInfo]
        self.current_fn_return_type = None
        self.ir_method_names = set()
        self.current_struct = None
        self.current_member_fn = None
        self.pending_member_calls = []

    def error(self, node, message):
        raise CompileError(f"line {node.line}:{node.col}: {message}")

    def lookup_local(self, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name]
        return None

    def check_assignable(self, expr, want, at, what):
        have = expr.type
        if have == want or (have == "i32" and want == "i64"):
            return
        if isinstance(expr, ConstNode) and want == "i32" and have == "i64":
            self.error(expr, f"constant {expr.value} does not fit in i32")
        self.error(at, f"cannot {what} of type {want} with a value of type {have}")

    def visit_program(self, node):
        # Pass 1: Check and register structs
        for struct in node.structs:
            struct.accept(self)

        for struct in node.structs:
            self.register_struct_methods(struct)
            
        # Pass 2: Collect all function signatures
        for fn in node.functions:
            self.register_function_signature(fn)
            
        # Pass 3a: Check member function bodies FIRST
        for struct in node.structs:
            struct_info = self.structs[struct.name]
            for method in struct.methods:
                self.visit_member_fn(method, struct_info)
                
        # Pass 3b: Fixed-Point Loop for mutating flag 
        changed = True
        while changed:
            changed = False
            for st in self.structs.values():
                for m in st.methods.values():
                    if not m.mutating:
                        for target_st, callee_name in m.this_calls:
                            if self.structs[target_st].methods[callee_name].mutating:
                                m.mutating = True
                                changed = True
                                
        for call_node in self.pending_member_calls:
            self.verify_member_call_mutation(call_node)
            
        # Pass 3c: Check global function bodies and top-level statements
        for fn in node.functions:
            fn.accept(self)
            
        for stmt in node.statements:
            stmt.accept(self)
            
        node.exit.accept(self)

    def visit_struct(self, node):
        if node.name in self.structs:
            self.error(node, f"struct '{node.name}' is already defined")
        
        fields_dict = {}
        is_deeply_mut = True
        
        for idx, field in enumerate(node.fields):
            if field.name in fields_dict:
                self.error(field, f"duplicate field '{field.name}' in struct '{node.name}'")
            
            if field.type_name not in ("i32", "i64", "bool") and field.type_name not in self.structs:
                self.error(field, f"unknown type '{field.type_name}' for field '{field.name}'")
                
            fields_dict[field.name] = FieldInfo(field.type_name, field.mutable, idx)
            
            if not field.mutable:
                is_deeply_mut = False
            elif field.type_name in self.structs:
                if not self.structs[field.type_name].is_deeply_mut:
                    is_deeply_mut = False
                    
        self.structs[node.name] = StructInfo(node.name, fields_dict, is_deeply_mut)

    def register_struct_methods(self, node):
        struct_info = self.structs[node.name]
        
        for method in node.methods:
            # Check for name collisions with fields and other methods
            if method.name in struct_info.fields:
                self.error(method, "field and member function cannot have the same name")
            if method.name in struct_info.methods:
                self.error(method, "duplicate member function")
                
            # Check for IR name collisions (e.g. struct A_B { fn c } vs struct A { fn B_c })
            ir_name = f"{node.name}_{method.name}"
            if ir_name in self.ir_method_names:
                self.error(method, f"IR name '{ir_name}' is already taken")
            self.ir_method_names.add(ir_name)
            
            # Validate parameter names and types
            param_names = set()
            for p in method.params:
                if p.name in param_names:
                    self.error(p, f"duplicate parameter '{p.name}' in member function '{method.name}'")
                param_names.add(p.name)
                
                if p.type_name not in ("i32", "i64", "bool") and p.type_name not in self.structs:
                    self.error(p, f"unknown type '{p.type_name}' for parameter '{p.name}'")
                    
            # Validate return type
            if method.return_type not in ("i32", "i64", "bool") and method.return_type not in self.structs:
                self.error(method, f"unknown return type '{method.return_type}'")
                
            # Register the member function
            struct_info.methods[method.name] = MemberFnInfo(
                method.name, node.name, method.params, method.return_type, method
            )

    def register_function_signature(self, node):
        if node.name in self.functions or node.name in self.structs:
            self.error(node, f"name '{node.name}' is already defined")
            
        param_names = set()
        for p in node.params:
            if p.name in param_names:
                self.error(p, f"duplicate parameter '{p.name}' in function '{node.name}'")
            param_names.add(p.name)
            
            if p.type_name not in ("i32", "i64", "bool") and p.type_name not in self.structs:
                self.error(p, f"unknown type '{p.type_name}' for parameter '{p.name}'")
                
        if node.return_type not in ("i32", "i64", "bool") and node.return_type not in self.structs:
            self.error(node, f"unknown return type '{node.return_type}'")
            
        self.functions[node.name] = FnInfo(node.name, node.params, node.return_type)

    def visit_member_fn(self, node, struct_info):
        method_info = struct_info.methods[node.name]
        
        saved_struct = self.current_struct
        saved_method = self.current_member_fn
        saved_ret_type = self.current_fn_return_type
        saved_scopes = self.scopes
        
        self.current_struct = struct_info
        self.current_member_fn = method_info
        self.current_fn_return_type = node.return_type
        self.scopes = [{}]  # top-level variables are hidden!
        
        for p in node.params:
            decl = DeclNode(p.line, p.col, p.name, p.type_name, False, [])
            self.scopes[0][p.name] = decl
            
        this_decl = DeclNode(node.line, node.col, "this", struct_info.name, True, None)
        node.this_decl = this_decl
        
        for stmt in node.body.statements:
            stmt.accept(self)
            
        if node.body.exit:
            node.body.exit.accept(self)
            
        self.current_struct = saved_struct
        self.current_member_fn = saved_method
        self.current_fn_return_type = saved_ret_type
        self.scopes = saved_scopes

    def visit_function(self, node):
        saved_scopes = self.scopes
        self.scopes = [{}]

        for p in node.params:
        # Parameters are copies and cannot be changed in the body, so mutable=False
            decl = DeclNode(p.line, p.col, p.name, p.type_name, False, [])
            self.scopes[0][p.name] = decl

        self.current_fn_return_type = node.return_type
        for stmt in node.body.statements:
            stmt.accept(self)
        if node.body.exit:
            node.body.exit.accept(self)

        self.scopes = saved_scopes
        self.current_fn_return_type = None

    def visit_decl(self, node):
        if node.name in self.scopes[-1]:
            self.error(node, f"variable '{node.name}' is already declared in this block")
            
        type_name = node.type_name
        if type_name not in ("i32", "i64", "bool") and type_name not in self.structs:
            self.error(node, f"unknown type '{type_name}'")

        if type_name in ("i32", "i64", "bool"):
            if len(node.init.values) != 1:
                self.error(node.init, f"expected exactly 1 initializer for {type_name}")
            val = node.init.values[0]
            if isinstance(val, InitListNode):
                self.error(val, "nested {} initializer not allowed for built-in types")
            have = val.accept(self)
            self.check_assignable(val, type_name, node, f"initialise '{node.name}'")
        else:
            struct_info = self.structs[type_name]
            node.is_copy_init = False
            
            # Check for whole-object copy
            if len(node.init.values) == 1 and not isinstance(node.init.values[0], InitListNode):
                val = node.init.values[0]
                have = val.accept(self)
                if have == type_name:
                    node.is_copy_init = True
                    
            if not node.is_copy_init:
                self.check_initializer(node.init, node.init.values, struct_info)

        self.scopes[-1][node.name] = node

    def check_initializer(self, context_node, values, struct_info):
        if len(values) != len(struct_info.fields):
            self.error(context_node, f"wrong number of values in {{}}: expected {len(struct_info.fields)}, got {len(values)}")
            
        for val, (f_name, f_info) in zip(values, struct_info.fields.items()):
            if isinstance(val, InitListNode):
                if f_info.type_name not in self.structs:
                    self.error(val, f"nested {{}} initializer not allowed for field '{f_name}' of type {f_info.type_name}")
                val.struct_type = f_info.type_name
                self.check_initializer(val, val.values, self.structs[f_info.type_name])
            else:
                have = val.type if val.type is not None else val.accept(self)
                if f_info.type_name in self.structs:
                    if have != f_info.type_name:
                        self.error(val, f"cannot initialize field '{f_name}' of type {f_info.type_name} with {have}")
                else:
                    self.check_assignable(val, f_info.type_name, val, f"initialize field '{f_name}'")

    def visit_assign(self, node):
        decl = self.lookup_local(node.name)
        node.is_this_field = False
        node.field_indices = []
        
        if decl is not None:
            node.decl = decl
            if not decl.mutable:
                self.error(node, f"cannot assign to constant variable '{node.name}'")
            current_type = decl.type_name
            
        elif self.current_struct is not None and node.name in self.current_struct.fields:
            node.is_this_field = True
            node.this_decl = self.current_member_fn.node.this_decl
            
            f_info = self.current_struct.fields[node.name]
            if not f_info.is_mut:
                self.error(node, f"cannot assign through const field '{node.name}'")
                
            node.field_indices.append(f_info.index)
            current_type = f_info.type_name
            self.current_member_fn.mutating = True
            
        elif node.name in self.structs:
            self.error(node, f"'{node.name}' is a type, not a variable")
            
        else:
            self.error(node, f"variable '{node.name}' is used before its declaration")
            
        for f_name in node.fields:
            if current_type not in self.structs:
                self.error(node, f"cannot access field '{f_name}' on non-struct type {current_type}")
            struct_info = self.structs[current_type]
            if f_name not in struct_info.fields:
                self.error(node, f"unknown field '{f_name}' in struct '{current_type}'")
            f_info = struct_info.fields[f_name]
            
            if not f_info.is_mut:
                self.error(node, f"cannot assign through const field '{f_name}'")
                
            node.field_indices.append(f_info.index)
            current_type = f_info.type_name
            
        if current_type in self.structs:
            if not self.structs[current_type].is_deeply_mut:
                self.error(node, f"':=' can replace a whole mut object only if all its fields, at every depth, are mut")
                
        node.value.accept(self)
        self.check_assignable(
            node.value, current_type, node, f"assign to '{node.name}{'.' + '.'.join(node.fields) if node.fields else ''}'"
        )

    def visit_exit(self, node):
        have_type = node.value.accept(self)
        
        if self.current_fn_return_type is not None:
            want_type = self.current_fn_return_type
            if have_type != want_type and not (have_type == "i32" and want_type == "i64"):
                self.error(node, f"exit of the wrong type in a function: expected {want_type}, got {have_type}")
        else:
            if have_type not in ("i32", "i64", "bool"):
                self.error(node, f"cannot exit with type {have_type} at top level")

    def visit_binop(self, node):
        lt = node.left.accept(self)
        rt = node.right.accept(self)

        if node.op in ("+", "-", "*"):
            if lt not in ("i32", "i64") or rt not in ("i32", "i64"):
                bad_type = lt if lt not in ("i32", "i64") else rt
                self.error(node, f"cannot apply '{node.op}' to {bad_type}")
            node.type = "i64" if ("i64" in (lt, rt)) else "i32"
        elif node.op in ("==", "!="):
            both_int = lt in ("i32", "i64") and rt in ("i32", "i64")
            both_bool = lt == "bool" and rt == "bool"
            if not (both_int or both_bool):
                self.error(node, f"cannot compare {lt} with {rt}")
            node.type = "bool"
        else:
            self.error(node, f"unknown operator '{node.op}'")

        return node.type

    def visit_var(self, node):
        decl = self.lookup_local(node.name)

        if decl is not None:
            node.decl = decl
            node.type = decl.type_name
            node.is_this_field = False
            return node.type
            
        if self.current_struct is not None and node.name in self.current_struct.fields:
            node.is_this_field = True
            node.this_decl = self.current_member_fn.node.this_decl
            node.field_index = self.current_struct.fields[node.name].index
            node.type = self.current_struct.fields[node.name].type_name
            return node.type
            
        if node.name in self.structs:
            self.error(node, f"'{node.name}' is a type, not a variable")
            
        self.error(node, f"variable '{node.name}' is used before its declaration")

    def visit_const(self, node):
        if node.value <= I32_MAX and node.value >= I32_MIN:
            node.type = "i32"
        elif node.value <= I64_MAX and node.value >= I64_MIN:
            node.type = "i64"
        else:
            self.error(node, f"constant {node.value} does not fit in i64")
        return node.type

    def visit_bool(self, node):
        node.type = "bool"
        return node.type

    def visit_block(self, node):
        self.scopes.append({})
        for stmt in node.statements: stmt.accept(self)
        if node.exit: node.exit.accept(self)
        self.scopes.pop()

    def visit_if(self, node):
        cond_type = node.condition.accept(self)
        if cond_type != "bool":
            self.error(node, f"the condition of 'if' must be bool, got {cond_type}")
        
        node.then_block.accept(self)
        if node.else_block:
            node.else_block.accept(self)

    def visit_while(self, node):
        cond_type = node.condition.accept(self)
        if cond_type != "bool":
            self.error(node, f"the condition of 'while' must be bool, got {cond_type}")

        node.body.accept(self)

    def visit_not(self, node):
        operand_type = node.value.accept(self)
        if operand_type != "bool":
            self.error(node, f"cannot apply '!' to {operand_type}")
        
        node.type = "bool"
        return node.type

    def visit_field(self, node):
        node.field_indices = []
        
        if getattr(node, 'target', None) is not None:
            current_type = node.target.accept(self)
            if current_type not in self.structs:
                raise CompileError(f"line {node.dot_line}:{node.dot_col}: cannot use '.' after a call that returns {current_type}")
            node.is_rvalue = True
        else:
            decl = self.lookup_local(node.base_name)
            
            if decl is not None:
                node.decl = decl
                node.is_this_field = False
                current_type = decl.type_name
                
            elif self.current_struct is not None and node.base_name in self.current_struct.fields:
                node.is_this_field = True
                node.this_decl = self.current_member_fn.node.this_decl
                node.field_indices.append(self.current_struct.fields[node.base_name].index)
                current_type = self.current_struct.fields[node.base_name].type_name
                
            elif node.base_name in self.structs:
                self.error(node, f"'{node.base_name}' is a type, not a variable")
                
            else:
                self.error(node, f"variable '{node.base_name}' is used before its declaration")

        for f_name in node.fields:
            if current_type not in self.structs:
                self.error(node, f"cannot access field '{f_name}' on non-struct type {current_type}")
            struct_info = self.structs[current_type]
            if f_name not in struct_info.fields:
                self.error(node, f"unknown field '{f_name}' in struct '{current_type}'")
            f_info = struct_info.fields[f_name]
            node.field_indices.append(f_info.index)
            current_type = f_info.type_name
            
        node.type = current_type
        return current_type
    
    def visit_call(self, node):
        if self.current_struct is not None and node.func_name in self.current_struct.methods:
            # It is a call to a member function on the same object (this)!
            node.is_this_call = True
            node.this_decl = self.current_member_fn.node.this_decl
            fn_decl = self.current_struct.methods[node.func_name]
            node.fn_decl = fn_decl
            self.current_member_fn.this_calls.add((self.current_struct.name, node.func_name))
        else:
            node.is_this_call = False
            if node.func_name not in self.functions:
                self.error(node, f"unknown function '{node.func_name}'")
            fn_decl = self.functions[node.func_name]
            node.fn_decl = fn_decl
        
        if len(node.args) != len(fn_decl.params):
            self.error(node, f"wrong number of arguments for '{node.func_name}': expected {len(fn_decl.params)}, got {len(node.args)}")

        node.widen_args = []
        for arg, param in zip(node.args, fn_decl.params):
            arg_type = arg.accept(self)
            if arg_type == param.type_name:
                node.widen_args.append(False)
            elif arg_type == "i32" and param.type_name == "i64":
                node.widen_args.append(True)
            else:
                self.error(arg, f"cannot pass {arg_type} as {param.type_name} for parameter '{param.name}'")
                
        node.type = fn_decl.return_type
        return node.type

    def visit_member_call(self, node):
        target_type = node.target.accept(self)
        
        if target_type not in self.structs:
            raise CompileError(f"line {node.dot_line}:{node.dot_col}: cannot call member function '{node.name}' on non-struct type {target_type}")
            
        struct_info = self.structs[target_type]
        if node.name not in struct_info.methods:
            self.error(node, f"struct '{target_type}' has no member function '{node.name}'")
            
        fn_info = struct_info.methods[node.name]
        
        if len(node.args) != len(fn_info.params):
            self.error(node, f"wrong number of arguments for '{node.name}': expected {len(fn_info.params)}, got {len(node.args)}")
            
        node.widen_args = []
        for arg, param in zip(node.args, fn_info.params):
            arg_type = arg.accept(self)
            if arg_type == param.type_name:
                node.widen_args.append(False)
            elif arg_type == "i32" and param.type_name == "i64":
                node.widen_args.append(True)
            else:
                self.error(arg, f"cannot pass {arg_type} as {param.type_name} for parameter '{param.name}'")
                
        node.fn_decl = fn_info
        node.struct_name = target_type
        node.type = fn_info.return_type
        
        # If calling on a field of 'this', record it in the current member function's this_calls
        if getattr(node.target, 'is_this_field', False):
            if self.current_member_fn is not None:
                self.current_member_fn.this_calls.add((target_type, node.name))
                
        # Defer mutation check if we are inside a member function body (fixed-point loop hasn't run yet)
        if self.current_member_fn is not None:
            self.pending_member_calls.append(node)
        else:
            self.verify_member_call_mutation(node)
            
        return node.type

    def verify_member_call_mutation(self, node):
        if getattr(node, 'is_this_call', False):
            # Implicit call directly on 'this'. 'this' is always mutable, caller becomes mutating via fixed-point.
            return
            
        fn_info = node.fn_decl
        if fn_info.mutating:
            if not self.is_path_mutable(node.target):
                from nodes import VarNode, FieldNode
                if isinstance(node.target, VarNode):
                    path_str = node.target.name
                elif isinstance(node.target, FieldNode):
                    if getattr(node.target, 'is_rvalue', False):
                        path_str = "call_result." + '.'.join(node.target.fields)
                    else:
                        path_str = node.target.base_name + '.' + '.'.join(node.target.fields)
                else:
                    path_str = "expression"
                self.error(node, f"cannot call mutating method '{node.name}' on const path '{path_str}'")

    def is_path_mutable(self, target):
        from nodes import VarNode, FieldNode, CallNode, MemberCallNode

        # A temporary root object (call result) is always mutable.
        if isinstance(target, (CallNode, MemberCallNode)):
            return True
            
        if not isinstance(target, (VarNode, FieldNode)):
            return False
            
        if getattr(target, 'is_rvalue', False):
            # For a FieldNode on a call result, we verify the intermediate fields are mut.
            curr_type = target.target.type
            for f_name in target.fields:
                f_info = self.structs[curr_type].fields[f_name]
                if not f_info.is_mut:
                    return False
                curr_type = f_info.type_name
            return True
            
        if getattr(target, 'is_this_field', False):
            struct_name = target.this_decl.type_name
            struct_info = self.structs[struct_name]
            
            if isinstance(target, VarNode):
                return struct_info.fields[target.name].is_mut
                
            if isinstance(target, FieldNode):
                if not struct_info.fields[target.base_name].is_mut:
                    return False
                curr_type = struct_info.fields[target.base_name].type_name
                for f_name in target.fields:
                    f_info = self.structs[curr_type].fields[f_name]
                    if not f_info.is_mut:
                        return False
                    curr_type = f_info.type_name
                return True
        else:
            if not target.decl.mutable:
                return False
                
            if isinstance(target, FieldNode):
                curr_type = target.decl.type_name
                for f_name in target.fields:
                    f_info = self.structs[curr_type].fields[f_name]
                    if not f_info.is_mut:
                        return False
                    curr_type = f_info.type_name
            return True

    def visit_read(self, node):
        node.type = "i32"
        return "i32"

    def visit_print(self, node):
        if node.is_string:
            return None
            
        arg_type = node.arg.accept(self)
        if arg_type not in ("i32", "i64", "bool") and arg_type not in self.structs:
            self.error(node.arg, f"cannot print value of type {arg_type}")
