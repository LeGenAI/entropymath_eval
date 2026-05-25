
import os
import json
import glob
import numpy as np
import re
from sympy import parse_expr, simplify, N
from sympy.parsing.latex import parse_latex

# Configuration
BASE_DIR = "/Users/imds/Desktop/Eval-MATH/math_eval_v7/outputs/problems_will_be_open"
OUTPUT_FILE = os.path.join(BASE_DIR, "analysis_report.tex")

# Categorization
CATEGORIES = {
    "Local - KR": [
        "hcx-007", "a.x-4.0-light", "solar-pro2", 
        "exaone-4.0.1-32b", "llama-varco-8b-instruct", "ax4"
    ],
    "Local - US": [
        "gpt-oss-20b", "gemma-3-27b"
    ],
    "Local - CN": [
        "qwen3-30b-a3b-2507", "deepseek-v3.2", "deepseek-r1-distill-qwen-32b"
    ]
}

# Assuming anything not in Local lists is API if it's in the directory, 
# or we can manually define API list.
# Let's treat valid models not in Local as API.

# --- GRADING LOGIC START ---
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
    text = extract_boxed(text)
    text = text.replace("\\", "").replace(" ", "").strip()
    return text

def convert_frac(text):
    while "\\frac{" in text:
        start = text.find("\\frac{")
        balance = 1
        i = start + 6
        while i < len(text) and balance > 0:
            if text[i] == '{': balance += 1
            elif text[i] == '}': balance -= 1
            i += 1
        if balance != 0: break 
        arg1_end = i - 1
        arg1 = text[start+6 : arg1_end]
        
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
            replacement = f"({arg1})/({arg2})"
            text = text[:start] + replacement + text[j:]
        else:
            break
    return text

def is_equiv(pred, gold):
    norm_pred = normalize_text(pred)
    norm_gold = normalize_text(gold)
    if norm_pred == norm_gold:
        return True
    
    def clean_for_sympy(s):
        s = extract_boxed(s)
        s = s.strip()
        s = s.replace("\\$", "").replace("$", "")
        s = s.replace("\\%", "/100").replace("%", "/100")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        s = s.replace("\\degree", "*pi/180").replace("^{\\circ}", "*pi/180").replace("^\\circ", "*pi/180")
        s = s.replace("\\,", "").replace("\\;", "").replace("\\:", "").replace("\\ ", "")
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\pi", "pi")
        s = convert_frac(s)
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
        try:
            expr_pred = parse_latex(clean_pred)
            expr_gold = parse_latex(clean_gold)
        except Exception:
            local_dict = {'frac': lambda x, y: x/y}
            expr_pred = parse_expr(clean_pred, local_dict=local_dict)
            expr_gold = parse_expr(clean_gold, local_dict=local_dict)
            
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
# --- GRADING LOGIC END ---

def get_category(model_name):
    # Normalize model name for matching
    # Remove vendor prefix for matching or match partial
    norm_name = model_name.split('/')[-1]
    
    for cat, models in CATEGORIES.items():
        for m in models:
            if m.lower() in norm_name.lower():
                return cat
            if norm_name.lower() in m.lower(): # Reverse check
                return cat
                
    return "API / Others"

def main():
    print(f"Scanning {BASE_DIR}...")
    
    model_stats = {}
    
    for root, dirs, files in os.walk(BASE_DIR):
        json_files = [f for f in files if f.endswith('.json') and not f.startswith('summary')]
        
        if not json_files:
            continue
            
        rel_path = os.path.relpath(root, BASE_DIR)
        model_name = rel_path
        
        if model_name in model_stats:
            continue
            
        print(f"Processing model: {model_name}...")
        
        # Structure:
        # problems[id] = [bool_run0, bool_run1, bool_run2]
        stats = {
            'problems': {}, 
            'total_attempts': 0,
            'correct_attempts': 0,
            'total_problems_with_at_least_one_run': 0
        }
        
        # Pre-scan to group by run
        for jf in json_files:
            try:
                with open(os.path.join(root, jf), 'r') as f:
                    data = json.load(f)
                    
                pid = data.get('id')
                if pid is None: continue
                
                final_answer = data.get('final_answer', "")
                gold_answer = data.get('gold_answer', "")
                is_correct = is_equiv(final_answer, gold_answer)
                
                if pid not in stats['problems']:
                    stats['problems'][pid] = []
                
                stats['problems'][pid].append(is_correct)
                
                stats['total_attempts'] += 1
                if is_correct:
                    stats['correct_attempts'] += 1
                    
            except Exception as e:
                print(f"Error reading {jf}: {e}")

        # Compute accuracy based on total attempts
        if stats['total_attempts'] > 0:
            stats['accuracy'] = stats['correct_attempts'] / stats['total_attempts']
            
            # Calculate Pass@3 (Solved Rate: at least one correct run)
            # Assuming n=3 mostly. Pass@3 ~ prob of >=1 correct.
            solved_count = 0
            total_probs = len(stats['problems'])
            for pid, runs in stats['problems'].items():
                if any(runs):
                    solved_count += 1
            
            stats['pass_at_3'] = solved_count / total_probs if total_probs > 0 else 0.0
            stats['category'] = get_category(model_name)
            model_stats[model_name] = stats

    generate_latex(model_stats)
    export_json(model_stats)

def generate_latex(model_stats):
    # Group models by category
    grouped_models = {}
    for name, stats in model_stats.items():
        cat = stats['category']
        if cat not in grouped_models:
            grouped_models[cat] = []
        grouped_models[cat].append((name, stats))
        
    # Sort models within groups by accuracy (or pass@3? User usually prefers acc or pass@3. Let's keep acc for now or maybe pass@3)
    # Let's keep sorting by accuracy for consistency, or maybe pass@3. Accuracy is usually finer grained (average).
    for cat in grouped_models:
        grouped_models[cat].sort(key=lambda x: x[1]['accuracy'], reverse=True)
        
    # Categories Order
    cat_order = ["API / Others", "Local - KR", "Local - US", "Local - CN"]
    
    latex_content = [
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\usepackage[table]{xcolor}",
        r"\usepackage[margin=0.5in]{geometry}",
        r"\usepackage{caption}",
        r"\usepackage{adjustbox}",
        r"\captionsetup{font=small}",
        r"\definecolor{score3}{RGB}{144, 238, 144}",  # Light Green (3/3)
        r"\definecolor{score2}{RGB}{255, 255, 224}",  # Light Yellow (2/3)
        r"\definecolor{score1}{RGB}{255, 218, 185}",  # Peach/Orange (1/3)
        r"\definecolor{score0}{RGB}{255, 182, 193}",  # Light Red (0/3)
        r"",
        r"\begin{document}",
        r"\section*{Math Evaluation Report}",
        r"",
        r"\begin{table}[h!]",
        r"\centering",
        r"\small",
    ]

    # Collect all PIDs first to ensure consistent columns
    all_pids = set()
    for _, stats in model_stats.items():
        all_pids.update(stats['problems'].keys())
    sorted_pids = sorted(list(all_pids))
    
    # Table Header
    # Added one column for Pass@3
    col_def = "l c c " + "c"*len(sorted_pids)
    latex_content.append(r"\begin{tabular}{" + col_def + r"}")
    latex_content.append(r"\toprule")
    
    header_row = r"\textbf{Model} & \textbf{Acc} & \textbf{Pass@3} "
    for pid in sorted_pids:
        header_row += r" & \textbf{" + str(pid) + r"}"
    header_row += r" \\"
    latex_content.append(header_row)
    
    # Iterate through Categories
    for cat in cat_order:
        if cat not in grouped_models:
            continue
            
        models = grouped_models[cat]
        
        # Section Header
        latex_content.append(r"\midrule")
        # Multicolumn for category title: Model + Acc + Pass@3 + PIDs
        total_cols = 3 + len(sorted_pids)
        latex_content.append(r"\multicolumn{" + str(total_cols) + r"}{l}{\textbf{" + cat + r"}} \\")
        latex_content.append(r"\midrule")
        
        for name, stats in models:
            display_name = name.split('/')[-1].replace("_", r"\_")
            # Truncate
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            
            acc_str = f"{stats['accuracy']:.1%}".replace('%', r'\%')
            pass3_str = f"{stats['pass_at_3']:.1%}".replace('%', r'\%')
            
            row = f"{display_name} & {acc_str} & {pass3_str}"
            
            for pid in sorted_pids:
                runs = stats['problems'].get(pid, [])
                if not runs:
                    cell = "-" 
                else:
                    correct_count = sum(runs)
                    total_runs_for_problem = len(runs)
                    
                    # Determine color
                    if correct_count == total_runs_for_problem and correct_count > 0:
                        color = "score3" # Perfect
                    elif correct_count == 0:
                        color = "score0" # Fail
                    else:
                        ratio = correct_count / total_runs_for_problem
                        if ratio >= 0.66:
                            color = "score2" # Mostly correct
                        else:
                            color = "score1" # Mostly wrong
                    
                    # Exact override if 3 runs (standard)
                    if total_runs_for_problem == 3:
                        if correct_count == 3: color = "score3"
                        elif correct_count == 2: color = "score2"
                        elif correct_count == 1: color = "score1"
                        elif correct_count == 0: color = "score0"

                    cell = r"\cellcolor{" + color + r"} " + f"{correct_count}/{total_runs_for_problem}"
                
                row += f" & {cell}"
            
            row += r" \\"
            latex_content.append(row)
            
    latex_content.append(r"\bottomrule")
    latex_content.append(r"\end{tabular}")
    latex_content.append(r"\caption{Pass rates (Correct Runs / Total Runs). Green=3/3, Yellow=2/3, Orange=1/3, Red=0/3.}")
    latex_content.append(r"\end{table}")

    latex_content.append(r"\end{document}")
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write("\n".join(latex_content))
    
    print(f"Report generated at: {OUTPUT_FILE}")

def export_json(model_stats):
    JSON_PATH = os.path.join(BASE_DIR, "leaderboard_data.json")
    
    # Prepare data structure for frontend
    # We want: 
    # {
    #   "categories": { "Category Name": [ { model_data }, ... ] },
    #   "sorted_pids": [0, 1, 2...]
    # }
    
    # Collect all PIDs
    all_pids = set()
    for _, stats in model_stats.items():
        all_pids.update(stats['problems'].keys())
    sorted_pids = sorted(list(all_pids))
    
    export_data = {
        "categories": {},
        "sorted_pids": sorted_pids
    }
    
    # helper for category
    # Reuse global CATEGORIES or simple logic
    # Actually we already have stats['category']
    
    cat_order = ["API / Others", "Local - KR", "Local - US", "Local - CN"]
    
    # Group manually to respect order
    grouped = {c: [] for c in cat_order}
    
    for name, stats in model_stats.items():
        cat = stats.get('category', "API / Others")
        if cat not in grouped: # Should be covered if logic matches, but safety
            if cat not in cat_order:
                # Add dynamic category if not in order list
                cat_order.append(cat)
                grouped[cat] = []
        
        # Format model data
        display_name = name.split('/')[-1]
        
        # Prepare per-problem stats
        problem_stats = {}
        for pid in sorted_pids:
            runs = stats['problems'].get(pid, [])
            if not runs:
                problem_stats[pid] = None
            else:
                problem_stats[pid] = {
                    "correct": sum(runs),
                    "total": len(runs)
                }
                
        model_entry = {
            "id": name,
            "name": display_name,
            "accuracy": stats['accuracy'],
            "pass_at_3": stats.get('pass_at_3', 0.0),
            "avg_turns": stats.get('avg_turns', 0),
            "tool_use_rate": stats.get('tool_use_rate', 0),
            "problem_stats": problem_stats
        }
        
        grouped[cat].append(model_entry)
        
    # Sort models in each group
    for cat in grouped:
        grouped[cat].sort(key=lambda x: x['accuracy'], reverse=True)
        
    # Finalize structure (only include non-empty categories in order)
    final_cats = {}
    for cat in cat_order:
        if grouped[cat]:
            final_cats[cat] = grouped[cat]
            
    export_data["categories"] = final_cats
    
    with open(JSON_PATH, 'w') as f:
        json.dump(export_data, f, indent=2)
        
    print(f"Leaderboard JSON exported to: {JSON_PATH}")

if __name__ == "__main__":
    main()
