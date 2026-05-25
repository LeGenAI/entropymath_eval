import os
import json
import glob
import argparse
import re
from sympy import parse_expr, simplify, N
from sympy.parsing.latex import parse_latex
from sympy.core.sympify import SympifyError

def extract_boxed(text):
    if not text:
        return ""
    text = str(text)
    if "\\boxed{" in text:
        start = text.find("\\boxed{") + 7
        balance = 1
        end = start
        while end < len(text) and balance > 0:
            if text[end] == '{':
                balance += 1
            elif text[end] == '}':
                balance -= 1
            end += 1
        if balance == 0:
            return text[start:end-1]
    return text

def normalize_text(text):
    # Destructive normalization for simple string match
    text = extract_boxed(text)
    text = text.replace("\\", "").replace(" ", "").strip()
    return text

def convert_frac(text):
    while "\\frac{" in text:
        start = text.find("\\frac{")
        # Find first arg
        balance = 1
        i = start + 6
        while i < len(text) and balance > 0:
            if text[i] == '{': balance += 1
            elif text[i] == '}': balance -= 1
            i += 1
        if balance != 0: break # Error or incomplete
        arg1_end = i - 1
        arg1 = text[start+6 : arg1_end]
        
        # Check for second arg start
        if i < len(text) and text[i] == '{':
            balance = 1
            j = i + 1
            while j < len(text) and balance > 0:
                if text[j] == '{': balance += 1
                elif text[j] == '}': balance -= 1
                j += 1
            if balance != 0: break
            arg2_end = j - 1
            arg2 = text[i+1 : arg2_end]
            
            # Replace
            replacement = f"({arg1})/({arg2})"
            text = text[:start] + replacement + text[j:]
        else:
            break # Malformed \frac
    return text

def is_equiv(pred, gold):
    # 1. Exact string match (normalized)
    norm_pred = normalize_text(pred)
    norm_gold = normalize_text(gold)
    if norm_pred == norm_gold:
        return True
        
    # 2. Sympy comparison
    # Clean up strings for sympy parsing
    def clean_for_sympy(s):
        s = extract_boxed(s) # Only extract boxed, don't strip backslashes yet
        s = s.strip()
        
        # Remove common non-math text or formatting that might confuse parser
        s = s.replace("\\$", "") # Remove dollar signs
        s = s.replace("$", "")
        s = s.replace("\\%", "/100") # Handle percentage
        s = s.replace("%", "/100")
        # Handle common latex commands
        s = s.replace("\\dfrac", "\\frac") # normalize dfrac to frac
        s = s.replace("\\tfrac", "\\frac") # normalize tfrac to frac
        
        # Handle degrees: 120^{\circ} -> 120 * pi / 180
        # Simple regex for number followed by ^{\circ} or \degree
        # We'll do a simple replacement for now, assuming the number is immediately before
        # But actually, sympy might not like "120 * pi / 180" mixed with other things if not careful.
        # Let's just replace \degree and ^{\circ} with "*pi/180"
        s = s.replace("\\degree", "*pi/180")
        s = s.replace("^{\\circ}", "*pi/180")
        s = s.replace("^\\circ", "*pi/180")
        s = s.replace("\\,", "") # remove thin spaces
        s = s.replace("\\;", "") # remove thick spaces
        s = s.replace("\\:", "") # remove medium spaces
        s = s.replace("\\ ", "") # remove escaped spaces
        
        s = s.replace("\\left", "") # remove \left
        s = s.replace("\\right", "") # remove \right
        s = s.replace("\\pi", "pi") # replace pi
        
        # Convert frac manually
        s = convert_frac(s)
        
        # Convert powers ^{...} to **(...)
        # Simple regex for ^{...}
        # Note: This handles simple cases. Nested braces might need a loop like convert_frac
        # But for now let's try a simple loop similar to convert_frac if needed, 
        # or just a regex if we assume no nesting in powers for these simple numbers.
        # Let's use a robust loop approach similar to convert_frac to be safe.
        while "^{" in s:
            start = s.find("^{")
            balance = 1
            i = start + 2
            while i < len(s) and balance > 0:
                if s[i] == '{': balance += 1
                elif s[i] == '}': balance -= 1
                i += 1
            if balance != 0: break
            content = s[start+2 : i-1]
            replacement = f"**({content})"
            s = s[:start] + replacement + s[i:]
            
        return s

    clean_pred = clean_for_sympy(pred)
    clean_gold = clean_for_sympy(gold)

    try:
        # Try parsing as latex
        # Note: parse_latex needs antlr4-python3-runtime installed. 
        # If not available, we might fallback to parse_expr if it looks like python math
        
        # Attempt 1: parse_latex
        try:
            expr_pred = parse_latex(clean_pred)
            expr_gold = parse_latex(clean_gold)
        except Exception:
            # Attempt 2: parse_expr (standard sympy parser)
            # This works better for simple arithmetic or python-like syntax
            # We need to define 'frac' if we replaced \frac with it
            local_dict = {'frac': lambda x, y: x/y}
            expr_pred = parse_expr(clean_pred, local_dict=local_dict)
            expr_gold = parse_expr(clean_gold, local_dict=local_dict)
            
        # Compare
        # Handle tuples/lists element-wise
        if isinstance(expr_pred, (list, tuple)) and isinstance(expr_gold, (list, tuple)):
            if len(expr_pred) != len(expr_gold):
                return False
            for p, g in zip(expr_pred, expr_gold):
                diff = simplify(p - g)
                if diff != 0:
                    # Try numerical fallback for elements
                    if abs(N(p) - N(g)) > 1e-6:
                        return False
            return True
            
        # Method A: simplify(a - b) == 0
        diff = simplify(expr_pred - expr_gold)
        if diff == 0:
            return True
            
        # Method B: Numerical evaluation
        val_pred = N(expr_pred)
        val_gold = N(expr_gold)
        if abs(val_pred - val_gold) < 1e-6:
            return True
            
    except Exception:
        # Fallback to simple float conversion if possible
        try:
            f_pred = float(clean_pred)
            f_gold = float(clean_gold)
            if abs(f_pred - f_gold) < 1e-6:
                return True
        except ValueError:
            pass
        
    return False

def evaluate_model(model_dir):
    if not os.path.exists(model_dir):
        print(f"Directory not found: {model_dir}")
        return

    files = glob.glob(os.path.join(model_dir, "*_run_*.json"))
    total = 0
    correct = 0
    tool_usage = 0
    
    print(f"Evaluating results in: {model_dir}")
    
    results = []

    for file_path in sorted(files):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
            
        total += 1
        problem_id = data.get('id')
        final = data.get('final_answer', "")
        gold = data.get('gold_answer', "")
        history = data.get('history', [])
        
        # Check tool usage
        used_tool = any(m.get('role') == 'tool' for m in history)
        if used_tool:
            tool_usage += 1
            
        # Check correctness
        # Use the 'solved' field if we trust it, but user asked to check results.
        # The previous inspection showed 'solved' might be wrong.
        # Let's do our own check.
        
        # However, implementing a full math grader is hard. 
        # Let's try to use the 'solved' field as a baseline but verify it?
        # Actually, the user said "results check" (confirming performance).
        # Let's trust our is_equiv for now, but also print if it differs from 'solved'.
        
        is_correct = is_equiv(final, gold)
        
        if is_correct:
            correct += 1
        else:
            # Debug print for incorrect
            # print(f"FAIL ID {problem_id}: Pred='{final}' | Gold='{gold}'")
            pass
            
        results.append({
            "id": problem_id,
            "correct": is_correct,
            "tool_used": used_tool,
            "final": final,
            "gold": gold
        })

    print(f"Total Files: {total}")
    print(f"Accuracy: {correct}/{total} ({correct/total*100:.2f}%)")
    print(f"Tool Usage: {tool_usage}/{total} ({tool_usage/total*100:.2f}%)")
    
    # Save detailed results
    output_file = os.path.join(model_dir, "evaluation_summary.json")
    with open(output_file, 'w') as f:
        json.dump({
            "metrics": {
                "accuracy": correct/total if total > 0 else 0,
                "tool_usage": tool_usage/total if total > 0 else 0,
                "total": total,
                "correct": correct
            },
            "details": results
        }, f, indent=2)
    print(f"Detailed results saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", type=str, required=True, help="Path to model output directory")
    args = parser.parse_args()
    
    evaluate_model(args.model_dir)
