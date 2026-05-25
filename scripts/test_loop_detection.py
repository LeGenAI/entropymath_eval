
import unittest
from unittest.mock import MagicMock
from math_eval_v7.solvers.tool_solver import ToolSolver

class TestToolSolverLoopDetection(unittest.TestCase):
    def test_loop_detection(self):
        # Mock config
        config = {
            "model": "test-model",
            "base_url": "http://localhost:1234/v1",
            "api_key": "test",
            "temperature": 0.0,
            "stop": ["[PYTHON]"]
        }
        
        solver = ToolSolver(config)
        
        # Mock API Client
        solver.client = MagicMock()
        
        # Scenario:
        # 1. Model generates "Thought: I will calculate 1+1."
        # 2. Tool output (simulated or skipped)
        # 3. Model generates "Thought: I will calculate 1+1." (LOOP)
        # 4. Solver should detect loop and inject user message.
        # 5. Model generates "Answer: \boxed{2}" (Recovery)
        
        solver.client.chat_completion.side_effect = [
            "Thought: I will calculate 1+1.", # Turn 0
            "Thought: I will calculate 1+1.", # Turn 1 (Loop)
            "Answer: \\boxed{2}"              # Turn 2 (Recovery after intervention)
        ]
        
        # Mock Python Tool to avoid actual execution overhead
        solver.python_tool = MagicMock()
        solver.python_tool.run.return_value = "2"
        
        # Run solve
        result = solver.solve("What is 1+1?")
        
        # Verify history
        history = result['history']
        
        # Check if loop detection message was injected
        # The history list in solve() contains assistant and tool messages.
        # The user messages are in the 'messages' list inside solve(), which isn't returned directly in 'history' usually,
        # but let's check the flow.
        
        # We expect:
        # 1. Assistant: "Thought: I will calculate 1+1."
        # 2. (Loop detected, no assistant message added for the duplicate)
        # 3. Assistant: "Answer: \boxed{2}"
        
        print("History:", history)
        
        # If loop detection works, the duplicate message should NOT be in history, 
        # OR it might be skipped.
        # In my implementation:
        # if loop detected:
        #    messages.append(user_warning)
        #    continue
        # So the duplicate assistant message is NOT added to history.
        
        assistant_messages = [h['content'] for h in history if h['role'] == 'assistant']
        self.assertEqual(len(assistant_messages), 2)
        self.assertEqual(assistant_messages[0], "Thought: I will calculate 1+1.")
        self.assertEqual(assistant_messages[1], "Answer: \\boxed{2}")
        
        print("Loop detection test passed!")

if __name__ == '__main__':
    unittest.main()
