# pylint: disable=missing-docstring

import os
import pathlib
import unittest
from typing import Optional, List, Sequence, Dict

from aas_smt_from_ifc import parse
import tests.common


class TestLex(unittest.TestCase):
    # pylint: disable=protected-access

    def assert_token_kinds(
        self,
        tokens: Sequence[parse._Token],
        expected: Sequence[parse._TokenKind],
        message: Optional[str] = None,
    ) -> None:
        self.assertSequenceEqual(expected, [token.kind for token in tokens], message)

    def test_empty(self) -> None:
        tokens, ok = parse._lex("")
        assert ok
        self.assertEqual([], tokens)

    def test_keywords_case_insensitive(self) -> None:
        tokens, ok = parse._lex("entity Wall; end_entity;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.ENTITY,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_ENTITY,
                parse._TokenKind.SEMI,
            ],
        )

    def test_keyword_boundaries(self) -> None:
        # Keywords should not match as substrings inside identifiers.
        tokens, ok = parse._lex("ANDY ORBIT END_ENTITYX iffy thenx")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.IDENTIFIER,
            ],
        )

    def test_schema_header_footer(self) -> None:
        tokens, ok = parse._lex("SCHEMA Ifc4x3; END_SCHEMA;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.SCHEMA,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_SCHEMA,
                parse._TokenKind.SEMI,
            ],
        )

    def test_self_backslash_qualification(self) -> None:
        tokens, ok = parse._lex(r"WHERE SELF\IfcRoot.GlobalId = 'abc';")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.WHERE,
                parse._TokenKind.SELF,
                parse._TokenKind.BACKSLASH,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.DOT,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.EQ,
                parse._TokenKind.STRING_LITERAL,
                parse._TokenKind.SEMI,
            ],
        )

    def test_backslash_inside_string_is_not_tokenized(self) -> None:
        tokens, ok = parse._lex(r"'A\X2\00E9\X0\B';")
        assert ok
        kinds = [t.kind for t in tokens]
        self.assert_token_kinds(
            tokens, [parse._TokenKind.STRING_LITERAL, parse._TokenKind.SEMI]
        )
        self.assertNotIn(parse._TokenKind.BACKSLASH, kinds)
        self.assertEqual(r"'A\X2\00E9\X0\B'", tokens[0].text)

    def test_string_with_quote_escape(self) -> None:
        tokens, ok = parse._lex(r"'O\'Reilly';")
        assert ok
        self.assert_token_kinds(
            tokens, [parse._TokenKind.STRING_LITERAL, parse._TokenKind.SEMI]
        )
        self.assertEqual(r"'O\'Reilly'", tokens[0].text)

    def test_string_simple(self) -> None:
        tokens, ok = parse._lex("'hello';")
        assert ok
        self.assert_token_kinds(
            tokens, [parse._TokenKind.STRING_LITERAL, parse._TokenKind.SEMI]
        )

    def test_empty_block_comment(self) -> None:
        tokens, ok = parse._lex("(* *)")
        assert ok
        self.assert_token_kinds(tokens, [parse._TokenKind.COMMENT])

    def test_garbage_in_block_comment(self) -> None:
        tokens, ok = parse._lex("(* \ntrla baba lan \\ hello \n *)")
        assert ok
        self.assert_token_kinds(tokens, [parse._TokenKind.COMMENT])

    def test_comment_between_tokens(self) -> None:
        tokens, ok = parse._lex("ENTITY(*x*)A;END_ENTITY;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.ENTITY,
                parse._TokenKind.COMMENT,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_ENTITY,
                parse._TokenKind.SEMI,
            ],
        )

    def test_multiline_comment_between_tokens(self) -> None:
        tokens, ok = parse._lex("ENTITY(* something \n unimportant *)A;END_ENTITY;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.ENTITY,
                parse._TokenKind.COMMENT,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_ENTITY,
                parse._TokenKind.SEMI,
            ],
        )

    def test_multiple_multiline_comments_between_tokens(self) -> None:
        tokens, ok = parse._lex(
            """\
ENTITY
  (* 
    first comment block 
  *) 
  A 
  (*
    another comment block
  *)
  ;
  END_ENTITY;
"""
        )
        if not ok:
            if len(tokens) == 0:
                raise AssertionError("Failed to parse any tokens")

            tokens_joined = "\n".join(str(token) for token in tokens)
            raise AssertionError(
                "Failed to parse the two blocks; the tokens parsed so far:\n"
                f"{tokens_joined}"
            )

        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.ENTITY,
                parse._TokenKind.COMMENT,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.COMMENT,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_ENTITY,
                parse._TokenKind.SEMI,
            ],
        )

    def test_multiline_prolog_comment_from_IFC4_1_RC3_20170302_schema(self) -> None:
        # NOTE (mristin):
        # This test case failed on the first implementation of the lexer and we only
        # discovered it when we tried to parse the actual schema.

        tokens, ok = parse._lex(
            """\
(*
Copyright by:
buildingSMART International Limited, 1996-2017

Any technical documentation made available by buildingSMART International Limited
is the copyrighted work of buildingSMART International Limited and is owned by the 
buildingSMART International Limited. It may be photocopied, used in software development, 
or translated into another computer language without prior written consent from 
buildingSMART International Limited provided that full attribution is given. 
Prior written consent is required if changes are made to the technical specification.

This material is delivered to you as is and buildingSMART International Limited makes 
no warranty of any kind with regard to it, including, but not limited to, the implied 
warranties as to its accuracy or fitness for a particular purpose. Any use of the 
technical documentation or the information contained therein is at the risk of the user. 
Documentation may include technical or other inaccuracies or typographical errors. 
buildingSMART International Limited shall not be liable for errors contained therein or 
for incidental consequential damages in connection with the furnishing, performance or use 
of the material. The information contained in this document is subject to change without notice.

Issue date:
Thursday, March 2, 2017

*)

SCHEMA IFC4X1;
"""
        )
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.COMMENT,
                parse._TokenKind.SCHEMA,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
            ],
        )

    def test_numbers_with_signs_and_exponents(self) -> None:
        text = (
            "x : INTEGER = -10; y : REAL = 1.23E-3; z : REAL = 0.5; w : INTEGER = +42;"
        )
        tokens, ok = parse._lex(text)
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.COLON,
                parse._TokenKind.INTEGER,
                parse._TokenKind.EQ,
                parse._TokenKind.MINUS,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.SEMI,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.COLON,
                parse._TokenKind.REAL,
                parse._TokenKind.EQ,
                parse._TokenKind.REAL_LITERAL,
                parse._TokenKind.SEMI,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.COLON,
                parse._TokenKind.REAL,
                parse._TokenKind.EQ,
                parse._TokenKind.REAL_LITERAL,
                parse._TokenKind.SEMI,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.COLON,
                parse._TokenKind.INTEGER,
                parse._TokenKind.EQ,
                parse._TokenKind.PLUS,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.SEMI,
            ],
        )

    def test_real_does_not_require_digits_both_sides(self) -> None:
        tokens, ok = parse._lex(".5 . 1.")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.REAL_LITERAL,
                parse._TokenKind.DOT,
                parse._TokenKind.REAL_LITERAL,
            ],
        )

    def test_list_bounds_and_of(self) -> None:
        tokens, ok = parse._lex("LIST [1:10] OF STRING;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.LIST,
                parse._TokenKind.LSQ,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.COLON,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.RSQ,
                parse._TokenKind.OF,
                parse._TokenKind.STRING,
                parse._TokenKind.SEMI,
            ],
        )

    def test_parens_commas_whitespace(self) -> None:
        tokens, ok = parse._lex("crop \t   ( 20, 30, 40, 10 ) ;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.LPAR,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.COMMA,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.COMMA,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.COMMA,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.RPAR,
                parse._TokenKind.SEMI,
            ],
        )

    def test_dot_attribute_without_self(self) -> None:
        tokens, ok = parse._lex("IfcWall.GlobalId;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.DOT,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.SEMI,
            ],
        )

    def test_control_flow_tokens(self) -> None:
        tokens, ok = parse._lex("IF TRUE THEN x = 1; END_IF;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IF,
                parse._TokenKind.TRUE,
                parse._TokenKind.THEN,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.EQ,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_IF,
                parse._TokenKind.SEMI,
            ],
        )

    def test_lowercase(self) -> None:
        tokens, ok = parse._lex("if true then x = 1; end_if;")
        assert ok
        self.assert_token_kinds(
            tokens,
            [
                parse._TokenKind.IF,
                parse._TokenKind.TRUE,
                parse._TokenKind.THEN,
                parse._TokenKind.IDENTIFIER,
                parse._TokenKind.EQ,
                parse._TokenKind.INTEGER_LITERAL,
                parse._TokenKind.SEMI,
                parse._TokenKind.END_IF,
                parse._TokenKind.SEMI,
            ],
        )


TEST_DATA_DIR = pathlib.Path(os.path.realpath(__file__)).parent.parent / "test_data"


class TextLexOnSchemas(unittest.TestCase):
    # pylint: disable=protected-access

    def test_success_on_real_schemas(self) -> None:
        for path in sorted((TEST_DATA_DIR / "schemas").glob("*.exp")):
            text = path.read_text(encoding="utf-8")

            tokens, ok = parse._lex(text)
            if not ok:
                self.assertGreater(len(tokens), 0, "At least something parsed")

                last_token = tokens[-1]
                end = last_token.start + len(last_token.text)
                missing_text = text[end : end + 50]

                last_token_kinds = [token.kind.value for token in tokens[-10:]]
                self.fail(
                    f"Last tokens were: {last_token_kinds!r}, "
                    f"missing text: {missing_text!r}"
                )


class TestUnescapeStringToken(unittest.TestCase):
    # pylint: disable=protected-access

    def assert_ok(self, content: str, expected: str) -> None:
        value, err = parse._Parser._unescape_string_token(content)
        self.assertIsNone(err, f"Expected success, got error: {err!r}")
        self.assertEqual(value, expected)

    def assert_err(self, content: str, expected_substr: str) -> None:
        value, err = parse._Parser._unescape_string_token(content)
        self.assertIsNone(value, f"Expected error, got value: {value!r}")
        assert err is not None
        self.assertIn(expected_substr, err)

    # basic & simple escapes

    def test_plain_without_escapes(self) -> None:
        self.assert_ok("'hello'", "hello")

    def test_simple_newline_tab_quote_backslash(self) -> None:
        self.assert_ok("'a\\n\\tb\\'c\\\\d\\\"e'", "a\n\tb'c\\d\"e")

    def test_double_quote_escape(self) -> None:
        self.assert_ok("'say \\\"hi\\\"'", 'say "hi"')

    def test_unknown_escape_is_preserved_literally(self) -> None:
        # \q is not recognized; should stay as backslash + q
        self.assert_ok("'foo\\qbar'", "foo\\qbar")

    def test_mixed_simple_and_text(self) -> None:
        self.assert_ok(
            "'line1\\nline2 and a \\\\ slash'", "line1\nline2 and a \\ slash"
        )

    # \S\hh

    def test_S_hex_to_latin1(self) -> None:
        # \S\E9 -> 'é' (0xE9)
        self.assert_ok("'caf\\S\\E9'", "café")

    def test_S_escape_incomplete(self) -> None:
        # Missing two hex digits after \S\
        self.assert_err("'bad \\S\\'", "Incomplete \\S\\hh escape")

    def test_S_escape_invalid_hex(self) -> None:
        self.assert_err("'bad \\S\\GZ here'", "Invalid hex in \\S\\hh escape")

    # \X2\...\X0\ (UCS-4 / UTF-32-like)

    def test_X2_single_codepoint_grinning_face(self) -> None:
        # 😀 U+1F600
        self.assert_ok("'\\X2\\0001F600\\X0\\'", "😀")

    def test_X2_multiple_codepoints(self) -> None:
        # "A😀B"

        # fmt: off
        self.assert_ok(
            "'"
            "\\X2\\00000041\\X0\\"
            "middle"
            "\\X2\\0001F600\\X0\\"
            "\\X2\\00000042\\X0\\'",
            "Amiddle😀B"
        )
        # fmt: on

    def test_X2_unterminated(self) -> None:
        self.assert_err(
            "'start \\X2\\0001F600 something'", "Unterminated \\X2\\...\\X0\\ escape"
        )

    def test_X2_wrong_group_length(self) -> None:
        # 6 hex digits instead of a multiple of 8
        self.assert_err(
            "'\\X2\\0001F6\\X0\\'", "\\X2\\ block must be groups of 8 hex digits"
        )

    def test_X2_non_hex(self) -> None:
        self.assert_err(
            "'\\X2\\0001F6ZZ\\X0\\'", "\\X2\\ block must be groups of 8 hex digits"
        )

    # \X\...\X\ (UCS-2)

    def test_X_UCS2_basic_letter_A(self) -> None:
        # \X\0041\X\ -> 'A'
        self.assert_ok("'\\X\\0041\\X\\'", "A")

    def test_X_unterminated(self) -> None:
        self.assert_err("'broken \\X\\0041 text'", "Unterminated \\X\\...\\X\\ escape")

    def test_X_wrong_group_length(self) -> None:
        # 3 hex digits -> invalid
        self.assert_err("'\\X\\041\\X\\'", "\\X\\ block must be groups of 4 hex digits")

    def test_X_non_hex(self) -> None:
        self.assert_err(
            "'\\X\\00G1\\X\\'", "\\X\\ block must be groups of 4 hex digits"
        )

    def test_X_rejects_lone_surrogate(self) -> None:
        # High surrogate D83D should be rejected in UCS-2 context
        self.assert_err("'\\X\\D83D\\X\\'", "Lone surrogate in \\X\\ block")

    # structure & boundary conditions

    def test_dangling_backslash_at_end(self) -> None:
        self.assert_err(
            "'abc\\'", "Dangling backslash at the end of the string literal"
        )

    def test_missing_quotes(self) -> None:
        self.assert_err("abc", "Expected single quotes around the string literal")

    def test_input_too_short_empty(self) -> None:
        self.assert_err("", "only 0 character(s)")

    def test_input_too_short_len1(self) -> None:
        self.assert_err("'", "only 1 character(s)")


class TestParseExpr(unittest.TestCase):
    # pylint: disable=protected-access

    _UNARY_OP_TO_STRING: Dict[parse.UnaryOp, str] = {
        parse.UnaryOp.PLUS: "+",
        parse.UnaryOp.NEG: "-",
        parse.UnaryOp.NOT: "NOT",
    }

    _BINARY_OP_TO_STRING: Dict[parse.BinaryOp, str] = {
        # Arithmetic
        parse.BinaryOp.ADD: "+",
        parse.BinaryOp.SUBTRACT: "-",
        parse.BinaryOp.MULTIPLY: "*",
        parse.BinaryOp.REAL_DIVIDE: "/",
        parse.BinaryOp.INTEGER_DIVIDE: "DIV",
        parse.BinaryOp.MODULO: "MOD",
        parse.BinaryOp.POWER: "**",
        # Logical
        parse.BinaryOp.OR: "OR",
        parse.BinaryOp.XOR: "XOR",
        parse.BinaryOp.AND: "AND",
        # Collections
        parse.BinaryOp.CONCAT: "||",
        # Relational (value comparison)
        parse.BinaryOp.LESS_THAN: "<",
        parse.BinaryOp.GREATER_THAN: ">",
        parse.BinaryOp.LESS_EQUAL: "<=",
        parse.BinaryOp.GREATER_EQUAL: ">=",
        parse.BinaryOp.EQUAL: "=",
        parse.BinaryOp.NOT_EQUAL: "<>",
        # Instance comparison (entity identity)
        parse.BinaryOp.INSTANCE_EQUAL: ":=:",
        parse.BinaryOp.INSTANCE_NOT_EQUAL: ":<>:",
        # Membership / pattern match
        parse.BinaryOp.IN: "IN",
        parse.BinaryOp.LIKE: "LIKE",
    }

    @staticmethod
    def dump_expr(expr: parse.Expr) -> str:
        if isinstance(expr, parse.BinaryLiteral):
            return f"<binary literal for {expr.value!r}>"

        elif isinstance(expr, parse.IntegerLiteral):
            return str(expr.value)

        elif isinstance(expr, parse.LogicalLiteral):
            return expr.value.name

        elif isinstance(expr, parse.RealLiteral):
            return str(expr.value)

        elif isinstance(expr, parse.StringLiteral):
            return repr(expr.value)

        elif isinstance(expr, parse.AggregateLiteral):
            element_strs = []  # type: List[str]

            for element in expr.elements:
                value_str = TestParseExpr.dump_expr(element.expr)

                if element.repetition is None:
                    element_strs.append(value_str)
                else:
                    # noinspection PyTypeChecker
                    repetition = TestParseExpr.dump_expr(element.repetition)
                    element_strs.append(f"{value_str}: {repetition}")

            elements_joined = ", ".join(element_strs)

            return f"[{elements_joined}]"

        elif isinstance(expr, parse.IndeterminateLiteral):
            return "?"

        elif isinstance(expr, parse.Self):
            return "SELF"

        elif isinstance(expr, parse.NameRef):
            return expr.identifier

        elif isinstance(expr, parse.BinaryExpr):
            left = TestParseExpr.dump_expr(expr.left)
            right = TestParseExpr.dump_expr(expr.right)

            op = TestParseExpr._BINARY_OP_TO_STRING[expr.op]

            return f"({left}) {op} ({right})"

        elif isinstance(expr, parse.UnaryExpr):
            operand = TestParseExpr.dump_expr(expr.operand)

            op = TestParseExpr._UNARY_OP_TO_STRING[expr.op]

            return f"{op}({operand})"

        elif isinstance(expr, parse.AttributeRef):
            source = TestParseExpr.dump_expr(expr.source)

            return f"({source}).{expr.identifier}"

        elif isinstance(expr, parse.QualifiedAttributeRef):
            source = TestParseExpr.dump_expr(expr.source)

            return rf"({source})\{expr.group_qualifier}.{expr.attribute}"

        elif isinstance(expr, parse.IndexExpr):
            source = TestParseExpr.dump_expr(expr.source)
            index = TestParseExpr.dump_expr(expr.index)

            return rf"({source})[{index}]"

        elif isinstance(expr, parse.Call):
            callee = TestParseExpr.dump_expr(expr.callee)
            args_strs = []  # type: List[str]
            for arg in expr.args:
                if arg.name is not None:
                    args_strs.append(
                        f"""\
-- {arg.name} {TestParseExpr.dump_expr(arg.value)}"""
                    )
                else:
                    args_strs.append(TestParseExpr.dump_expr(arg.value))

            args_joined = ", ".join(args_strs)
            return f"({callee})({args_joined})"

        elif isinstance(expr, parse.Interval):
            left = TestParseExpr.dump_expr(expr.left)

            left_to_center = TestParseExpr._BINARY_OP_TO_STRING[expr.left_to_center]

            center = TestParseExpr.dump_expr(expr.center)

            center_to_right = TestParseExpr._BINARY_OP_TO_STRING[expr.center_to_right]

            right = TestParseExpr.dump_expr(expr.right)

            return (
                f"{{({left}) {left_to_center} ({center}) {center_to_right} ({right})}}"
            )

        elif isinstance(expr, parse.QueryExpr):
            aggregate = TestParseExpr.dump_expr(expr.aggregate)

            predicate = TestParseExpr.dump_expr(expr.predicate)

            return f"QUERY({expr.variable} <* {aggregate} | {predicate})"

        else:
            raise NotImplementedError(
                f"We have not implemented the dumping of expressions {type(expr)}"
            )

    def parse_and_dump_expr(self, text: str) -> str:
        tokens, ok = parse._lex(text)
        self.assertTrue(
            ok, f"Expected to lex, but failed for text: {text!r}; {tokens=}"
        )

        tape = parse._TokenTape(tokens=tokens)

        parser = parse._Parser(tape=tape)

        # noinspection PyArgumentList
        expr = parser._parse_expr()

        self.assertSequenceEqual([], parser.errors)
        assert expr is not None

        return TestParseExpr.dump_expr(expr)

    def test_literals(self) -> None:
        for text, expected in [
            ("%010101", r"<binary literal for b'\x15'>"),
            ("3", "3"),
            ("-3", "-(3)"),
            ("TRUE", "TRUE"),
            ("FALSE", "FALSE"),
            ("UNKNOWN", "UNKNOWN"),
            ("'hello world'", "'hello world'"),
            ("[4: 3, 'x']", "[4: 3, 'x']"),
            ("?", "?"),
        ]:
            dump = self.parse_and_dump_expr(text)
            self.assertEqual(expected, dump, f"Input was: {text=}")

    def test_primaries(self) -> None:
        for text, expected in [
            ("x", "x"),
            ("x[3]", "(x)[3]"),
            ("x.a", "(x).a"),
            ("doSomething(a, b)", "(doSomething)(a, b)"),
            ("SELF", "SELF"),
            (r"SELF\Something.a", r"(SELF)\Something.a"),
            ("{a < b < c}", "{(a) < (b) < (c)}"),
            ("QUERY(x <* Something | x > 0)", "QUERY(x <* Something | (x) > (0))"),
        ]:
            dump = self.parse_and_dump_expr(text)
            self.assertEqual(expected, dump, f"Input was: {text=}")

    def test_unaries(self) -> None:
        for text, expected in [
            ("NOT x", "NOT(x)"),
            ("NOT x[3]", "NOT((x)[3])"),
            ("-x.a", "-((x).a)"),
            ("-SELF", "-(SELF)"),
            (r"-SELF\Something.a", r"-((SELF)\Something.a)"),
        ]:
            dump = self.parse_and_dump_expr(text)
            self.assertEqual(expected, dump, f"Input was: {text=}")

    def test_binaries(self) -> None:
        for text, expected in [
            # Test for mix unary/postfix and binary
            ("NOT x + 1", "(NOT(x)) + (1)"),
            ("NOT x[3] + 1", "(NOT((x)[3])) + (1)"),
            ("-x.a + 1", "(-((x).a)) + (1)"),
            (r"-SELF\Something.a + 1", r"(-((SELF)\Something.a)) + (1)"),
            # Test for precedence addition-like
            ("a + b + c", "((a) + (b)) + (c)"),
            ("a - b - c", "((a) - (b)) - (c)"),
            # Test for precedence for concatenation
            ("a || b || c", "((a) || (b)) || (c)"),
            # Test for precedence multiplication-like
            ("a * b * c", "((a) * (b)) * (c)"),
            ("a / b / c", "((a) / (b)) / (c)"),
            ("a DIV b DIV c", "((a) DIV (b)) DIV (c)"),
            ("a MOD b MOD c", "((a) MOD (b)) MOD (c)"),
            ("a * b / c", "((a) * (b)) / (c)"),
            ("a / b * c", "((a) / (b)) * (c)"),
            ("a DIV b MOD c", "((a) DIV (b)) MOD (c)"),
            ("a MOD b DIV c", "((a) MOD (b)) DIV (c)"),
            ("a * b DIV c", "((a) * (b)) DIV (c)"),
            ("a * b + c", "((a) * (b)) + (c)"),
            # Test for precedence exponentiation
            ("a ** b ** c", "(a) ** ((b) ** (c))"),
            # Test for relational
            ("a < b ** c", "(a) < ((b) ** (c))"),
            # Test for logical
            ("a AND b OR c XOR d", "(((a) AND (b)) OR (c)) XOR (d)"),
            ("a OR b AND c", "(a) OR ((b) AND (c))"),
            # Test for logical and relational
            ("a < b AND b > c", "((a) < (b)) AND ((b) > (c))"),
            # Test for IN and LIKE
            ("a IN [b, c] OR a LIKE b", "((a) IN ([b, c])) OR ((a) LIKE (b))"),
        ]:
            dump = self.parse_and_dump_expr(text)
            self.assertEqual(expected, dump, f"Input was: {text=}")


class TestAgainstRecorded(unittest.TestCase):
    # pylint: disable=protected-access

    def test_against_golden_files(self) -> None:
        method_dirs = list(
            sorted((TEST_DATA_DIR / "test_parse" / "parse_method").iterdir())
        )

        selected_method_var = "AAS_SMT_FROM_IFC_TEST_PARSE_METHOD"
        selected_method = os.environ.get(selected_method_var, None)
        if selected_method is not None:
            if not hasattr(parse._Parser, selected_method):
                raise RuntimeError(
                    f"Unexpected selected method "
                    f"from environment variable {selected_method_var} "
                    f"-- it is not available in parse._Parser."
                )
            method_dirs = [
                (TEST_DATA_DIR / "test_parse" / "parse_method") / selected_method
            ]

        selected_case_var = "AAS_SMT_FROM_IFC_TEST_RECORD_CASE"
        selected_case = os.environ.get(selected_case_var, None)

        for method_dir in method_dirs:
            if not method_dir.is_dir():
                continue

            method_name = method_dir.name

            case_dirs = list(sorted(method_dir.iterdir()))

            if selected_case is not None:
                if selected_case not in [case_dir.name for case_dir in case_dirs]:
                    raise RuntimeError(
                        f"The case {selected_case} selected "
                        f"from environment variable {selected_case_var} "
                        f"is not available in {method_dir} directory."
                    )

                case_dirs = [method_dir / selected_case]

            for case_dir in case_dirs:
                if not case_dir.is_dir():
                    continue

                input_path = case_dir / "input.txt"

                text = input_path.read_text(encoding="utf-8")

                tokens, ok = parse._lex(text)
                assert ok, (
                    f"Unexpected error when parsing the text from {input_path}; "
                    f"last parsed token(s): {tokens[-10:]}"
                )

                tape = parse._TokenTape(tokens=tokens)

                parser = parse._Parser(tape=tape)

                method = getattr(parser, method_name, None)
                assert method is not None, (
                    f"Parser is missing the method {method_name!r} "
                    f"for the case {input_path}; either the test data is invalid "
                    f"or the {parse._Parser.__name__} code is invalid."
                )

                try:
                    result = method()
                except Exception as exception:
                    raise AssertionError(
                        f"Unexpected parsing failure "
                        f"for {method_name} on the case {case_dir.name}: {input_path}"
                    ) from exception

                if len(parser.errors) != 0:
                    errors_joined = ",\n".join(str(error) for error in parser.errors)
                    tokens_joined = ",\n".join(
                        str(token) for token in parser._tape._tokens
                    )

                    raise AssertionError(
                        f"Unexpected failure in {method_name} for {case_dir.name}:\n"
                        f"{errors_joined}\n\n"
                        f"last parsed token: {parser._last_parsed_token}\n"
                        f"tokens: [\n"
                        f"{tokens_joined}\n"
                        f"]"
                    )
                else:
                    assert result is not None

                dump = parse.dump(result)

                expected_dump_path = case_dir / "dump.txt"

                if tests.common.RECORDING:
                    expected_dump_path.write_text(dump, encoding="utf-8")
                else:
                    expected_dump = expected_dump_path.read_text(encoding="utf-8")

                    self.assertEqual(
                        expected_dump,
                        dump,
                        f"For the golden file {expected_dump_path}",
                    )


class TestOnRealSchemas(unittest.TestCase):
    def test_smoke(self) -> None:
        schema_paths = list(sorted((TEST_DATA_DIR / "schemas").glob("**/*.exp")))

        for schema_path in schema_paths:
            text = schema_path.read_text(encoding="utf-8")
            schema, errors = parse.parse(text)

            if errors is not None:
                errors_joined = ",\n".join(str(error) for error in errors)
                raise AssertionError(
                    f"Unexpected error(s) when parsing {schema_path}:\n"
                    f"{errors_joined}"
                )

            assert schema is not None

            # NOTE (mristin):
            # This is only a smoke test -- we test that we can successfully parse
            # the schema.


if __name__ == "__main__":
    unittest.main()
