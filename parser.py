from errors import CompileError
from nodes import ProgramNode, DeclNode, AssignNode, ExitNode, BinOpNode, VarNode, ConstNode

class Parser:
    def __init__(self, lines):
        # lines is a list of lists of tokens: [[Token, Token], [Token], ...]
        self.lines = lines
        self.toks = []
        self.pos = 0
        self.current_line_num = 1
        self.last_col = 1

    def error(self, message):
        """Raises a CompileError with the line and column of the error."""
        if self.pos < len(self.toks):
            tok = self.toks[self.pos]
            line, col = tok.line, tok.col
        else:
            line = self.current_line_num
            col = self.last_col
        CompileError(f"line {line}:{col}: {message}")

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None
    
    def eat(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok
    
    def expect(self, kind, what):
        tok = self.peek()
        if tok is None or tok.kind != kind: raise self.error(f"expected {what}")
        return self.eat()
    
    def parse_program(self):
        stmts = []
        exit_node = None

        for toks in self.lines:
            if not toks: 
                continue # Skip pure blank lines

            self.toks, self.pos = toks, 0
            self.current_line_num = toks[0].line
            # Default end of line column fallback if line fails immediately
            self.last_col = toks[-1].col + len(toks[-1].text) 
            
            if exit_node is not None:
                self.error("statement after exit")

            tok = self.peek()
            if tok.kind == "keyword" and tok.text == "exit":
                exit_node = self.parse_exitStmt()
            else:
                stmts.append(self.parse_statement())

            if self.peek() is not None:
                self.error(f"unexpected '{self.peek().text}' after the statement")

        if exit_node is None:
            CompileError(f"line {self.current_line_num}:{self.last_col}: program without exit")

        start_line = stmts[0].line if stmts else exit_node.line
        start_col = stmts[0].col if stmts else exit_node.col
        return ProgramNode(start_line, start_col, stmts, exit_node)

    def parse_statement(self):
        tok = self.peek()
        if tok is None:
            self.error("expected a statement, found end of line")
        
        if tok.kind == "keyword" and tok.text == "i32":
            return self.parse_decl()
        elif tok.kind == "ident":
            return self.parse_assign()
        else:
            self.error(f"cannot start a statement with '{tok.text}'")

    def parse_decl(self):
        tok = self.eat() # Eat "i32"
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
        
        return DeclNode(name.line, name.col, name.text, mutable, init)

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
            
        if tok.kind == "number":
            self.eat()
            return ConstNode(tok.line, tok.col, int(tok.text))
        elif tok.kind == "ident":
            self.eat()
            return VarNode(tok.line, tok.col, tok.text)
        else:
            self.error(f"expected a constant or a variable, got '{tok.text}'")