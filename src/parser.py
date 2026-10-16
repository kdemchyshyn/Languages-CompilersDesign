from errors import CompileError
from nodes import (
    ProgramNode, 
    StructNode, FieldDeclNode,
    FunctionNode, ParamNode,
    DeclNode, AssignNode, ExitNode, 
    BinOpNode, 
    VarNode, ConstNode, BoolNode, 
    FieldNode, CallNode,
    NotNode, 
    BlockNode, 
    IfNode, WhileNode,
    InitListNode
)

class Parser:
    def __init__(self, lines):
        # lines is a list of lists of tokens: [[Token, Token], [Token], ...]
        self.lines = lines
        self.line_idx = 0
        self.toks = []
        self.pos = 0
        self.current_line_num = 1
        self.last_col = 1
        self.TYPES = ["i32", "i64", "bool"] # Map from type name to type representation
        self.next_line()

    def error(self, message):
        """Raises a CompileError with the line and column of the error."""
        if self.pos < len(self.toks):
            tok = self.toks[self.pos]
            line, col = tok.line, tok.col
        else:
            line = self.current_line_num
            col = self.last_col

        raise CompileError(f"line {line}:{col}: {message}")

    def peek_line(self):
        """Looks ahead to the next line without consuming it."""
        return self.lines[self.line_idx] if self.line_idx < len(self.lines) else None

    def next_line(self):
        """Advances cursor to the next line and makes it current."""
        if self.line_idx < len(self.lines):
            self.toks = self.lines[self.line_idx]
            self.pos = 0
            if self.toks:
                self.current_line_num = self.toks[0].line
                self.last_col = self.toks[-1].col + len(self.toks[-1].text)
            self.line_idx += 1
            return True
        
        self.toks = []
        self.pos = 0
        return False

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None
    
    def eat(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok
    
    def expect(self, kind, what):
        tok = self.peek()
        if tok is None or tok.kind != kind: self.error(f"expected {what}")
        return self.eat()

    def expect_end_of_line(self, context="the statement"):
        """Ensures there are no trailing tokens on the current line."""
        if self.peek() is not None:
            self.error(f"unexpected '{self.peek().text}' after {context}")
    
    def parse_program(self):
        structs = []
        functions = []
        stmts = []
        exit_node = None

        # Loop 1: Parse struct declarations
        while self.toks and self.peek().kind == "keyword" and self.peek().text == "struct":
            structs.append(self.parse_struct())

        # Loop 2: Parse function declarations
        while self.toks and self.peek().kind == "keyword" and self.peek().text == "fn":
            functions.append(self.parse_fn())

        while self.toks:
            if exit_node is not None:
                self.error("statement after exit")

            tok = self.peek()
            if tok.kind == "keyword" and tok.text == "struct":
                self.error("struct declaration is not allowed after functions or statements")
            elif tok.kind == "keyword" and tok.text == "fn":
                self.error("function declaration is not allowed after statements")
            elif tok.kind == "keyword" and tok.text == "exit":
                exit_node = self.parse_exitStmt()
                self.expect_end_of_line("the statement")
                self.next_line()
            else:
                stmts.append(self.parse_statement())

        if exit_node is None:
            raise CompileError(f"line {self.current_line_num}:{self.last_col}: program without exit")

        start_line = (structs[0].line if structs else 
                      functions[0].line if functions else 
                      stmts[0].line if stmts else 
                      exit_node.line)
        start_col = (structs[0].col if structs else 
                     functions[0].col if functions else 
                     stmts[0].col if stmts else 
                     exit_node.col)
                     
        return ProgramNode(start_line, start_col, structs, functions, stmts, exit_node)

    def parse_struct(self):
        tok_struct = self.eat() # Eat "struct"
        name = self.expect("ident", "struct name")
        self.expect_end_of_line("struct declaration")
        
        next_l = self.peek_line()
        if next_l is None or next_l[0].text != "{":
            got = f"'{next_l[0].text}'" if next_l else "end of line"
            line = next_l[0].line if next_l else self.current_line_num
            col = next_l[0].col if next_l else self.last_col
            raise CompileError(f"line {line}:{col}: expected {'{'} on its own line after struct, got {got}")
        
        self.next_line()
        self.eat() # Eat "{"
        self.expect_end_of_line("the '{'")
        self.next_line()
        
        fields = []
        while self.toks and self.peek().text != "}":
            tok_type = self.peek()
            if tok_type.kind not in ("keyword", "ident"):
                self.error("expected a type for field")
            type_name = self.eat().text
            
            is_mut = False
            if self.peek() is not None and self.peek().text == "mut":
                self.eat()
                is_mut = True
                
            field_name = self.expect("ident", "field name")
            self.expect_end_of_line("field declaration")
            fields.append(FieldDeclNode(tok_type.line, tok_type.col, field_name.text, type_name, is_mut))
            self.next_line()
            
        if not fields:
            self.error("empty struct")
            
        if not self.toks or self.peek().text != "}":
            self.error("expected '}'")
        self.eat() # Eat "}"
        self.expect_end_of_line("the '}'")
        self.next_line()
        
        return StructNode(tok_struct.line, tok_struct.col, name.text, fields)

    def parse_fn(self):
        tok_fn = self.eat() # Eat "fn"
        name = self.expect("ident", "function name")
        
        self.expect("assign", "':='")
        self.expect("lparen", "'('")
        
        params = []
        if self.peek() is not None and self.peek().kind != "rparen":
            while True:
                tok_type = self.peek()
                if tok_type is None or tok_type.kind not in ("keyword", "ident"):
                    self.error("expected a type for parameter")
                type_name = self.eat().text
                
                param_name = self.expect("ident", "parameter name")
                params.append(ParamNode(tok_type.line, tok_type.col, param_name.text, type_name))
                
                if self.peek() is not None and self.peek().kind == "coma":
                    self.eat()
                else:
                    break
                    
        self.expect("rparen", "')'")
        self.expect("arrow", "'->'")
        
        ret_tok = self.peek()
        if ret_tok is None or ret_tok.kind not in ("keyword", "ident"):
            self.error("expected return type")
        ret_type = self.eat().text
        
        self.expect_end_of_line("function signature")
        
        next_l = self.peek_line()
        if next_l is None or next_l[0].text != "{":
            got = f"'{next_l[0].text}'" if next_l else "end of line"
            line = next_l[0].line if next_l else self.current_line_num
            col = next_l[0].col if next_l else self.last_col
            raise CompileError(f"line {line}:{col}: expected {'{'} on its own line after function signature, got {got}")
        
        self.next_line()
        body = self.parse_block("fn")
        
        if body.exit is None:
            raise CompileError(f"line {body.line}:{body.col}: function block must end with an exit statement")
            
        return FunctionNode(tok_fn.line, tok_fn.col, name.text, ret_type, params, body)

    def parse_statement(self):
        tok = self.peek()
        if tok is None:
            self.error("expected a statement, found end of line")

        if tok.kind == "keyword" and tok.text in ("struct", "fn"):
            self.error("function/struct declaration is not allowed after statements or inside a block")
        
        if (tok.kind == "keyword" and tok.text in self.TYPES) or tok.kind == "ident":
            is_decl = False
            if tok.kind == "keyword" and tok.text in self.TYPES:
                is_decl = True
            else:
                if self.pos + 1 < len(self.toks):
                    next_tok = self.toks[self.pos + 1]
                    if next_tok.kind == "keyword" and next_tok.text == "mut":
                        is_decl = True
                    elif next_tok.kind == "ident":
                        is_decl = True
                    elif next_tok.kind in ("assign", "dot"):
                        is_decl = False
                    elif next_tok.kind == "lparen":
                        self.error("A call alone is not a statement")
                    else:
                        self.error(f"unexpected token '{next_tok.text}' after '{tok.text}'")
                else:
                    self.error("incomplete statement")
                    
            if is_decl:
                node = self.parse_decl()
            else:
                node = self.parse_assign()
                
            self.expect_end_of_line("the statement")
            self.next_line()
            return node
        elif tok.kind == "keyword" and tok.text == "if":
            return self.parse_if()
        elif tok.kind == "keyword" and tok.text == "while":
            return self.parse_while()
        elif tok.kind == "keyword" and tok.text == "else":
            self.error("'else' without an 'if'")
        else:
            self.error(f"cannot start a statement with '{tok.text}'")

    def parse_if(self):
        tok_if = self.eat() # Eat "if"
        condition = self.parse_expr()
        
        # Verify nothing trails on the `if` line (preventing `if b {`)
        if self.peek() is not None:
            if self.peek().text == "{":
                self.error("unexpected '{' after the statement")
            else:
                self.expect_end_of_line("the statement")
        
        # Look ahead for '{' on its own line
        next_l = self.peek_line()
        if next_l is None or next_l[0].text != "{":
            got = f"'{next_l[0].text}'" if next_l else "end of line"
            line = next_l[0].line if next_l else self.current_line_num
            col = next_l[0].col if next_l else self.last_col
            raise CompileError(f"line {line}:{col}: expected {repr('{')} on its own line after 'if', got {got}")
        
        self.next_line()
        then_block = self.parse_block("if")
        
        # Optional else handling
        else_block = None
        if self.toks and self.peek() is not None and self.peek().text == "else":
            self.eat() # Eat "else"
            if self.peek() is not None:
                self.expect_end_of_line("the statement")
                
            next_l = self.peek_line()
            if next_l is None or next_l[0].text != "{":
                got = f"'{next_l[0].text}'" if next_l else "end of line"
                line = next_l[0].line if next_l else self.current_line_num
                col = next_l[0].col if next_l else self.last_col
                raise CompileError(f"line {line}:{col}: expected {repr('{')} on its own line after 'else', got {got}")
            
            self.next_line()
            else_block = self.parse_block("else")
            
        return IfNode(tok_if.line, tok_if.col, condition, then_block, else_block)

    def parse_while(self):
        tok_while = self.eat() # Eat "while"
        condition = self.parse_expr()

        # Verify nothing trails on the `while` line (preventing `while b {`)
        if self.peek() is not None:
            if self.peek().text == "{":
                self.error("unexpected '{' after the statement")
            else:
                self.expect_end_of_line("the statement")

        # Look ahead for '{' on its own line
        next_l = self.peek_line()
        if next_l is None or next_l[0].text != "{":
            got = f"'{next_l[0].text}'" if next_l else "end of line"
            line = next_l[0].line if next_l else self.current_line_num
            col = next_l[0].col if next_l else self.last_col
            raise CompileError(f"line {line}:{col}: expected {repr('{')} on its own line after 'while', got {got}")

        self.next_line()
        body = self.parse_block("while")

        return WhileNode(tok_while.line, tok_while.col, condition, body)

    def parse_block(self, after_what):
        tok_brace = self.eat() # Eat "{"
        self.expect_end_of_line("the statement")
        self.next_line()
        
        stmts = []
        exit_node = None
        
        while self.toks:
            tok = self.peek()
            
            if tok.text == "}":
                self.eat()
                self.expect_end_of_line("the statement")
                self.next_line()
                
                if not stmts and exit_node is None:
                    raise CompileError(f"line {tok_brace.line}:{tok_brace.col}: empty block")
                
                return BlockNode(tok_brace.line, tok_brace.col, stmts, exit_node)
            
            if exit_node is not None:
                self.error("statement after 'exit' in the same block")
            
            if tok.kind == "keyword" and tok.text == "exit":
                exit_node = self.parse_exitStmt()
                self.expect_end_of_line("the statement")
                self.next_line()
            else:
                stmts.append(self.parse_statement())
                
        raise CompileError(f"line {tok_brace.line}:{tok_brace.col}: {repr('{')} is never closed")

    def parse_decl(self):
        type_tok = self.eat() # Eat a type keyword
        mutable = False
        
        if self.peek() is not None and self.peek().kind == "keyword" and self.peek().text == "mut":
            self.eat()
            mutable = True
            
        name = self.expect("ident", "a variable name")
        
        if self.peek() is None or self.peek().kind != "lbrace":
            self.error(f"variable '{name.text}' needs an initialiser in {{}}")
        
        init_node = self.parse_init_list()
        
        return DeclNode(name.line, name.col, name.text, type_tok.text, mutable, init_node)

    def parse_assign(self):
        name = self.eat() # We know it's ident from parse_statement
        
        fields = []
        while self.peek() is not None and self.peek().kind == "dot":
            self.eat()
            field_ident = self.expect("ident", "field name")
            fields.append(field_ident.text)
        
        tok = self.peek()
        if tok is None or tok.kind != "assign":
            got = f"'{tok.text}'" if tok else "end of line"
            path = ".".join([name.text] + fields)
            self.error(f"expected ':=' after '{path}', got {got}")
        self.eat() # Eat ":="
        
        value = self.parse_expr()
        return AssignNode(name.line, name.col, name.text, fields, value)

    def parse_exitStmt(self):
        tok = self.eat() # Eat "exit"
        value = self.parse_factor()
        return ExitNode(tok.line, tok.col, value)

    def parse_expr(self):
        node = self.parse_arith()
        if (tok := self.peek()) is not None and tok.kind == "operation" and tok.text in ("==", "!="):
            self.eat()
            node = BinOpNode(tok.line, tok.col, tok.text, node, self.parse_arith())
        return node

    def parse_arith(self):
        node = self.parse_term()
        while (tok := self.peek()) is not None and tok.kind == "operation" and tok.text in ("+", "-"):
            self.eat()
            node = BinOpNode(tok.line, tok.col, tok.text, node, self.parse_term())
        return node

    def parse_term(self): 
        node = self.parse_factor()
        while (tok := self.peek()) is not None and tok.kind == "operation" and tok.text == "*":
            self.eat()
            node = BinOpNode(tok.line, tok.col, tok.text, node, self.parse_factor())
        return node

    def parse_factor(self):
        tok = self.peek()
        if tok is None:
            self.error("expected a constant or a variable, found end of line")
            
        if tok.kind == "operation" and tok.text == "!":
            self.eat()
            return NotNode(tok.line, tok.col, self.parse_factor())
        elif tok.kind == "number":
            self.eat()
            return ConstNode(tok.line, tok.col, int(tok.text))
        elif tok.kind == "keyword" and tok.text in ("true", "false"):
            self.eat()
            return BoolNode(tok.line, tok.col, True if tok.text == "true" else False)
        elif tok.kind == "ident":
            ident_tok = self.eat()
            
            next_tok = self.peek()
            if next_tok is not None and next_tok.kind == "lparen":
                # CallNode
                self.eat() # Eat "("
                args = []
                if self.peek() is not None and self.peek().kind != "rparen":
                    args.append(self.parse_expr())
                    while self.peek() is not None and self.peek().kind == "coma":
                        self.eat()
                        args.append(self.parse_expr())
                self.expect("rparen", "')'")
                return CallNode(ident_tok.line, ident_tok.col, ident_tok.text, args)
            elif next_tok is not None and next_tok.kind == "dot":
                # FieldNode
                fields = []
                while self.peek() is not None and self.peek().kind == "dot":
                    self.eat()
                    field = self.expect("ident", "field name")
                    fields.append(field.text)
                return FieldNode(ident_tok.line, ident_tok.col, ident_tok.text, fields)
            else:
                return VarNode(ident_tok.line, ident_tok.col, ident_tok.text)
        elif tok.kind == "lparen":
            self.error("expected a constant or a variable, got '('")
        else:
            self.error(f"expected a constant or a variable, got '{tok.text}'")

    def parse_init_list(self):
        tok_lbrace = self.eat() # Eat "{"
        
        values = []
        values.append(self.parse_init_val())
        while self.peek() is not None and self.peek().kind == "coma":
            self.eat() # Eat ","
            values.append(self.parse_init_val())

        self.expect("rbrace", "'}'")
        
        return InitListNode(tok_lbrace.line, tok_lbrace.col, values)

    def parse_init_val(self):
        tok = self.peek()
        # If we see a '{', we enter a nested initialization list
        if tok is not None and tok.kind == "lbrace":
            return self.parse_init_list()
        # Otherwise, parse a standard expression
        else:
            return self.parse_expr()