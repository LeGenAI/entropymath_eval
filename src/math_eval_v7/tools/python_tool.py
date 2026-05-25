import subprocess
import sys
import ast
import io
import contextlib
import traceback

class PythonTool:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        # Pre-import common libraries for the execution environment
        self.globals = {}
        try:
            import math
            import sympy
            import numpy
            import scipy
            import pandas
            self.globals = {
                "math": math,
                "sympy": sympy,
                "sp": sympy, # Common alias
                "numpy": numpy,
                "np": numpy, # Common alias
                "scipy": scipy,
                "pandas": pandas,
                "pd": pandas # Common alias
            }
        except ImportError as e:
            print(f"Warning: Could not import some libraries: {e}")

    def _wrap_code_with_print(self, code: str) -> str:
        """
        Wraps the given code to print the result of the last expression,
        mimicking REPL behavior.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If it's a syntax error, just return the original code
            # The exec will catch it later.
            return code

        if not tree.body:
            return code

        last_node = tree.body[-1]
        if isinstance(last_node, ast.Expr):
            # If the last node is an expression, we want to print it
            # Remove the last node from the tree
            tree.body.pop()

            # Reconstruct the code for the preceding statements
            preceding_code = ""
            if tree.body:
                preceding_code = ast.unparse(tree) + "\n"

            # Add the print statement for the last expression
            return preceding_code + f"print({ast.unparse(last_node.value)})"
        else:
            # If the last node is not an expression (e.g., assignment, function def),
            # just execute normally.
            return code

    def run(self, code: str) -> str:
        # Create a buffer to capture stdout
        buffer = io.StringIO()
        
        # Wrap code to print the last expression if it's an expression
        wrapped_code = self._wrap_code_with_print(code)
        
        try:
            # Redirect stdout
            with contextlib.redirect_stdout(buffer):
                # Execute in a restricted namespace but with our pre-imported globals
                # We copy globals to avoid pollution between runs if desired, 
                # but for a session-like feel, we might want to persist. 
                # For now, let's persist to allow variable reuse across turns!
                exec(wrapped_code, self.globals)
                
            output = buffer.getvalue()
            return output.strip() if output else "No output"
            
        except Exception as e:
            # traceback.print_exc() # Optional: print to stderr for debugging
            return f"{type(e).__name__}: {str(e)}"

    def get_prompt_description(self) -> str:
        return """
"""
