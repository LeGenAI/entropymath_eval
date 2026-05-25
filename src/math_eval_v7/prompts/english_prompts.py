SYSTEM_PROMPT_ENGLISH_COT = """Solve the problem efficiently and clearly. Please reason step by step, and put your final answer within \\boxed{}.
"""

FEW_SHOT_EXAMPLES = [
    {
        "question": "What is 12 * 13?",
        "response": """[THOUGHT]
I need to calculate the product of 12 and 13. I will use Python to find the exact number.
[/THOUGHT]
[PYTHON]
print(12 * 13)
[/PYTHON]"""
    },
    {
        "question": "Solve for x in 2x + 5 = 15.",
        "response": """[THOUGHT]
I need to solve the linear equation. I will use the sympy library to solve for x algebraically.
[/THOUGHT]
[PYTHON]
from sympy import symbols, solve
x = symbols('x')
equation = 2*x + 5 - 15
solution = solve(equation, x)
print(solution)
[/PYTHON]"""
    }
]

RESUME_TRIGGER = "Tool output received. Continue from the last [THOUGHT] using that output; do not rerun the same code."
