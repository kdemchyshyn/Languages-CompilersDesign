from errors import CompileError

KEYWORDS = {b"i32": "keyword", b"mut": "keyword", b"exit": "keyword"}

class Token:
    def __init__(self, kind, text, line, col):
        self.kind = kind
        self.text = text
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.kind}, '{self.text}', {self.line}:{self.col})"

def is_alpha(b):
    if b > 127: return False
    return b is not None and (chr(b).isalpha() or chr(b) == '_')

def is_digit(b):
    if b > 127: return False
    return b is not None and chr(b).isdigit()

def lex(data: bytes):
    lines, tokens = [], []
    state, start, line, col = "START", 0, 1, 1
    blocks = 0
    i = 0
    while i <= len(data): # one extra step: the end of input
        b = data[i] if i < len(data) else None
        if state == "START":
            if b is None: 
                if blocks > 0: raise CompileError(f"line {line}:{col}: {repr("{")} is not closed before the end of the line")
                else: break
            elif b in (32, 9): pass # space, tab
            elif b == 10: 
                if blocks > 0: raise CompileError(f"line {line}:{col}: {repr("{")} is not closed before the end of the line")
                elif tokens: lines.append(tokens); tokens = []; line += 1; col = 0
            elif is_alpha(b): state, start = "IDENT", i
            elif is_digit(b): state, start = "NUMBER", i
            elif b == ord("{"): tokens.append(Token("lbrace", "{", line, col)); blocks += 1
            elif b == ord("+"): tokens.append(Token("operation", "+", line, col))
            elif b == ord("-"): tokens.append(Token("operation", "-", line, col))
            elif b == ord("*"): tokens.append(Token("operation", "*", line, col))
            elif b == ord("}"): 
                tokens.append(Token("rbrace", "}", line, col))
                if blocks == 0: raise CompileError(f"line {line}:{col}: {repr("}")} is not opened in the line") 
                else: blocks -= 1
            elif b == ord(":"): state, start = "ASSIGN", i
            else: raise CompileError(f"line {line}:{col}: unexpected byte {repr(chr(b))}")
        elif state == "IDENT":
            if b is not None and (is_alpha(b) or is_digit(b)): pass
            else:
                word = data[start:i]
                tokens.append(Token(KEYWORDS.get(word, "ident"), word.decode(), line, col - len(word)))
                state = "START"; continue # re-read this byte in START
        elif state == "NUMBER": 
            if b is not None and is_digit(b): pass
            elif b is not None and is_alpha(b): raise CompileError(f"line {line}:{col}: a letter inside a number {data[start:i+1].decode()}")
            else:
                number = data[start:i]
                tokens.append(Token("number", number.decode(), line, col - len(number)))
                state = "START"; continue # re-read this byte in START
        elif state == "ASSIGN": 
            if b == ord("="): tokens.append(Token("assign", ":=", line, col - 1)); state = "START"
            else: raise CompileError(f"line {line}:{col}: a {repr(":")} not followed by {repr("=")}")
        i += 1; col += 1
    if tokens: lines.append(tokens)
    return lines
