import unittest
from unittest.mock import MagicMock, patch
from math_eval_v7.solvers.tool_solver import ToolSolver

class TestToolSolver(unittest.TestCase):
    @patch('math_eval_v7.solvers.tool_solver.APIClient')
    def test_solver_tool_use(self, MockAPIClient):
        # Setup mock
        mock_client = MockAPIClient.return_value
        mock_client.chat_completion.side_effect = [
            "Thought: I will use Python to calculate this.\n[PYTHON]\nprint(123 * 456)\n[/PYTHON]",
            "Thought: The result is 56088.\nFinal Answer: \\boxed{56088}"
        ]
        
        config = {"model": "test-model"}
        solver = ToolSolver(config)
        
        # Run solve
        result = solver.solve("123 * 456은?")
        
        # Verify
        self.assertTrue(result['solved'])
        self.assertEqual(result['final_answer'], "56088")
        self.assertEqual(len(result['history']), 3) # Assistant(Tool Call), Tool Output, Assistant(Final)
        
        # Check if tool was actually called (implicitly via history check or we can mock tool)
        # The history should contain the tool output
        self.assertIn("[PYTHON OUTPUT]", result['history'][1]['content'])
        self.assertIn("56088", result['history'][1]['content'])

if __name__ == '__main__':
    unittest.main()
