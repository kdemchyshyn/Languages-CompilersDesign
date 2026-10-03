from errors import CompileError
from nodes import ProgramNode, DeclNode, AssignNode, ExitNode, BinOpNode, VarNode, ConstNode, BoolNode, NotNode, BlockNode, IfNode

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
        stmts = []
        exit_node = None

        while self.toks:
            if exit_node is not None:
                self.error("statement after exit")

            tok = self.peek()
            if tok.kind == "keyword" and tok.text == "exit":
                exit_node = self.parse_exitStmt()
                self.expect_end_of_line("the statement")
                self.next_line()
            else:
                stmts.append(self.parse_statement())

        if exit_node is None:
            raise CompileError(f"line {self.current_line_num}:{self.last_col}: program without exit")

        start_line = stmts[0].line if stmts else exit_node.line
        start_col = stmts[0].col if stmts else exit_node.col
        return ProgramNode(start_line, start_col, stmts, exit_node)

    def parse_statement(self):
        tok = self.peek()
        if tok is None:
            self.error("expected a statement, found end of line")
        
        if tok.kind == "keyword" and tok.text in self.TYPES:
            node = self.parse_decl()
            self.expect_end_of_line("the statement")
            self.next_line()
            return node
        elif tok.kind == "ident":
            node = self.parse_assign()
            self.expect_end_of_line("the statement")
            self.next_line()
            return node
        elif tok.kind == "keyword" and tok.text == "if":
            return self.parse_if()
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
                    raise CompileError(f"line {tok.line}:{tok.col}: empty block")
                
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
        type = self.eat() # Eat a type keyword
        mutable = False
        
        if self.peek() is not None and self.peek().kind == "keyword" and self.peek().text == "mut":
            self.eat()
            mutable = True
            
        name = self.expect("ident", "a variable name")
        
        if self.peek() is None or self.peek().kind != "lbrace":
            self.error(f"variable '{name.text}' needs an initialiser in {{}}")
        self.eat() # Eat "{"
        
        init = self.parse_expr()
        self.expect("rbrace", "'}'")
        
        return DeclNode(name.line, name.col, name.text, type.text, mutable, init)

    def parse_assign(self):
        name = self.eat() # We know it's ident from parse_statement
        
        tok = self.peek()
        if tok is None or tok.kind != "assign":
            got = f"'{tok.text}'" if tok else "end of line"
            self.error(f"expected ':=' after '{name.text}', got {got}")
        self.eat() # Eat ":="
        
        value = self.parse_expr()
        return AssignNode(name.line, name.col, name.text, value)

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
            self.eat()
            return VarNode(tok.line, tok.col, tok.text)
        else:
            self.error(f"expected a constant or a variable, got '{tok.text}'")