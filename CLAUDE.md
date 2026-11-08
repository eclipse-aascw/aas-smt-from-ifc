# Claude Configuration

## Project Overview
This is about parsing Express schemas (used in IFC) in Python.
Claude assists with designing the parser.

## Key Files
- `relevant_grammars/` - Grammar of Express schema in G4; always consider it, together with the BNF of ISO 10303-11 at https://github.com/dustintownsend/EXPRESS-Modeling-Language-References/blob/master/iso-10303-11.bnf.
- `aas_smt_from_ifc/parser.py` - The central parser module
- `tests/` - Test files

## Coding Preferences
- Use immutable structures with `Final` for nodes of AST
- Follow the style of other `_parse_*` methods in `_Parser` class

## Communication Style
- Be concise but thorough
- Explain reasoning for architectural decisions
- Suggest alternatives when appropriate
