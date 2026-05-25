import os
import json
import glob
from sympy import parse_expr, simplify, N
from sympy.parsing.latex import parse_latex

# --- Copied from evaluate_performance.py ---

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
        try:
            expr_pred = parse_latex(clean_pred)
            expr_gold = parse_latex(clean_gold)
        except Exception:
            local_dict = {'frac': lambda x, y: x/y}
            expr_pred = parse_expr(clean_pred, local_dict=local_dict)
            expr_gold = parse_expr(clean_gold, local_dict=local_dict)
            
        # Compare
        if isinstance(expr_pred, (list, tuple)) and isinstance(expr_gold, (list, tuple)):
            if len(expr_pred) != len(expr_gold):
                return False
            for p, g in zip(expr_pred, expr_gold):
                diff = simplify(p - g)
                if diff != 0:
                    if abs(N(p) - N(g)) > 1e-6:
                        return False
            return True
            
        diff = simplify(expr_pred - expr_gold)
        if diff == 0:
            return True
            
        val_pred = N(expr_pred)
        val_gold = N(expr_gold)
        if abs(val_pred - val_gold) < 1e-6:
            return True
            
    except Exception:
        try:
            f_pred = float(clean_pred)
            f_gold = float(clean_gold)
            if abs(f_pred - f_gold) < 1e-6:
                return True
        except ValueError:
            pass
        
    return False

# --- End Copied Code ---

def regrade_all_files(outputs_dir):
    print(f"Scanning {outputs_dir}...")
    
    updated_count = 0
    total_count = 0
    correct_count = 0
    
    # Recursive walk for JSON files
    for root, dirs, files in os.walk(outputs_dir):
        for name in files:
            if name.endswith(".json") and "run" in name:
                file_path = os.path.join(root, name)
                total_count += 1
                
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        
                    final = data.get('final_answer', "")
                    gold = data.get('gold_answer', "")
                    original_solved = data.get('solved', False)
                    
                    # Re-grade
                    new_solved = is_equiv(final, gold)
                    
                    if new_solved:
                        correct_count += 1
                    
                    if new_solved != original_solved:
                        # Update file
                        data['solved'] = new_solved
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        updated_count += 1
                        print(f"[Updated] {name}: {original_solved} -> {new_solved}")
                        
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    print("-" * 30)
    print(f"Total Processed: {total_count}")
    print(f"Total Correct (After Regrade): {correct_count}")
    print(f"Files Updated: {updated_count}")

if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["outputs"]
    for target in targets:
        regrade_all_files(target)
