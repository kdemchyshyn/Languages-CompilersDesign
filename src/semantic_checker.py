from errors import CompileError
from nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode, BoolNode,
    BlockNode, IfNode, NotNode, WhileNode,
    InitListNode, FieldNode, CallNode, 
    StructNode, FunctionNode, ParamNode
)

I32_MAX = 2147483647
I32_MIN = -2147483648
I64_MAX = 9223372036854775807
I64_MIN = -9223372036854775808

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

    def error(self, node, message):
        raise CompileError(f"line {node.line}:{node.col}: {message}")

    def lookup(self, node, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name]
        self.error(node, f"variable '{name}' is used before its declaration")

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
            
        # Pass 2: Collect all function signatures
        for fn in node.functions:
            self.register_function_signature(fn)
            
        # Pass 3: Check function bodies and top-level statements
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

    def visit_function(self, node):
        saved_scopes = self.scopes
        self.scopes = [{}]
        
        for p in node.params:
            # Parameters are copies and cannot be changed in the body, so mutable=False
            decl = DeclNode(p.line, p.col, p.name, p.type_name, False, [])
            self.scopes[0][p.name] = decl
            
        self.current_fn_return_type = node.return_type
        node.body.accept(self)
        
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
                self.error(node, f"expected exactly 1 initializer for {type_name}")
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
                self.check_initializer(node, node.init.values, struct_info)

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
                have = val.accept(self)
                if f_info.type_name in self.structs:
                    if have != f_info.type_name:
                        self.error(val, f"cannot initialize field '{f_name}' of type {f_info.type_name} with {have}")
                else:
                    self.check_assignable(val, f_info.type_name, val, f"initialize field '{f_name}'")

    def visit_assign(self, node):
        decl = self.lookup(node, node.name)
        node.decl = decl
        
        if not decl.mutable:
            self.error(node, f"cannot assign to constant variable '{node.name}'")
            
        current_type = decl.type_name
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
            if lt == "bool" or rt == "bool":
                self.error(node, f"cannot apply '{node.op}' to bool")
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
        node.decl = self.lookup(node, node.name)
        node.type = node.decl.type_name
        return node.type

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
        decl = self.lookup(node, node.base_name)
        node.decl = decl
        current_type = decl.type_name
        
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
        if node.func_name not in self.functions:
            self.error(node, f"unknown function '{node.func_name}'")
        fn_info = self.functions[node.func_name]
        node.fn_decl = fn_info
        
        if len(node.args) != len(fn_info.params):
            self.error(node, f"wrong number of arguments for '{node.func_name}': expected {len(fn_info.params)}, got {len(node.args)}")
            
        for arg, param in zip(node.args, fn_info.params):
            arg_type = arg.accept(self)
            if arg_type == param.type_name:
                node.widen_args.append(False)
            elif arg_type == "i32" and param.type_name == "i64":
                node.widen_args.append(True)
            else:
                self.error(arg, f"cannot pass {arg_type} as {param.type_name} for parameter '{param.name}'")
                
        node.type = fn_info.return_type
        return node.type