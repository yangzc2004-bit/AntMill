#!/usr/bin/env python3
import sys
import os
import re

def main():
    # Parse arguments
    args = sys.argv[1:]
    if not args:
        print("Usage: python l2m.py INPUT_FILE [-o OUTPUT_FILE]", file=sys.stderr)
        sys.exit(1)
    
    input_file = args[0]
    output_file = None
    
    if len(args) >= 3 and args[1] == '-o':
        output_file = args[2]
    elif len(args) >= 2 and args[1] == '-o':
        print("Usage: python l2m.py INPUT_FILE [-o OUTPUT_FILE]", file=sys.stderr)
        sys.exit(1)
    
    # Check input file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except (FileNotFoundError, PermissionError, OSError):
        print(f"Error: cannot read '{input_file}'", file=sys.stderr)
        sys.exit(1)
    
    # Determine output file
    if output_file is None:
        basename = os.path.basename(input_file)
        if '.' in basename:
            basename = basename.rsplit('.', 1)[0] + '.md'
        else:
            basename = basename + '.md'
        output_file = os.path.join(os.getcwd(), basename)
    
    # Create parent directories if needed
    parent_dir = os.path.dirname(output_file)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    
    # Process the content
    result = process(content)
    
    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    
    sys.exit(0)

def process(content):
    lines = content.split('\n')
    
    # Step 1: Remove comments (first unescaped % on a line)
    # Also convert \% to % in the output
    processed_lines = []
    for line in lines:
        new_line = ''
        i = 0
        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line) and line[i + 1] == '%':
                # Escaped percent, output as literal %
                new_line += '%'
                i += 2
            elif line[i] == '%':
                # Unescaped percent, start of comment - stop here
                break
            else:
                new_line += line[i]
                i += 1
        processed_lines.append(new_line)
    
    # Step 2: Preamble and body selection
    full_text = '\n'.join(processed_lines)
    
    begin_doc = '\\begin{document}'
    end_doc = '\\end{document}'
    
    macros = {}
    
    if begin_doc in full_text:
        start = full_text.find(begin_doc)
        start_idx = start + len(begin_doc)
        
        end_idx = full_text.find(end_doc, start_idx)
        if end_idx == -1:
            body = full_text[start_idx:]
        else:
            body = full_text[start_idx:end_idx]
        
        # Extract preamble for macro definitions
        preamble = full_text[:start]
        macros = extract_macros(preamble)
    else:
        body = full_text
    
    # Strip leading/trailing whitespace from body to avoid extra newlines
    body = body.strip(' \t\n\r')
    
    # Step 3: Apply macro expansion to body
    if macros:
        body = expand_macros(body, macros)
    
    # Step 4: Process display math (multi-line and same-line)
    body = process_display_math(body)
    
    # Step 5: Process environments (enumerate, itemize, multicols, minipage)
    body = process_environments(body)
    
    # Step 6: Process parbox commands
    body = process_parbox(body)
    
    # Step 7: Process includegraphics commands
    body = process_includegraphics(body)
    
    # Step 8: Line stripping
    body_lines = body.split('\n')
    stripped_lines = [line.strip(' \t') for line in body_lines]
    
    # Step 9: Process each line for other conversions
    result_lines = []
    for line in stripped_lines:
        converted_line = apply_conversions(line)
        result_lines.append(converted_line)
    
    # Step 10: Blank line normalization
    text = '\n'.join(result_lines)
    
    # Collapse runs of 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip leading/trailing whitespace from final output
    text = text.strip(' \t\n\r')
    
    return text


def extract_macros(preamble):
    """Extract parameter-free macro definitions from preamble."""
    macros = {}
    
    # Pattern for \\def\\CMD{replacement}
    def_pattern = r'\\\\def\\\\([A-Za-z]+)\\{([^{}]*)\\}'
    
    # Find all \\def definitions
    for match in re.finditer(def_pattern, preamble):
        cmd = match.group(1)
        replacement = match.group(2)
        macros[cmd] = replacement
    
    # Pattern for \\newcommand{\\CMD}{replacement} (parameter-free)
    newcommand_pattern = r'\\\\newcommand\\{\\\\([A-Za-z]+)\\}\\{([^{}]*)\\}'
    
    # Find all \\newcommand definitions
    for match in re.finditer(newcommand_pattern, preamble):
        cmd = match.group(1)
        replacement = match.group(2)
        macros[cmd] = replacement
    
    # Filter out parameterized \\newcommand definitions
    # Pattern for \\newcommand{\\CMD}[N]{...} - parameterized
    param_newcommand_pattern = r'\\\\newcommand\\{\\\\([A-Za-z]+)\\}\\[\\d+\\]'
    for match in re.finditer(param_newcommand_pattern, preamble):
        cmd = match.group(1)
        if cmd in macros:
            del macros[cmd]
    
    return macros

def expand_macros(text, macros):
    """Expand macros in text, detecting cycles."""
    # Check for cycles first
    if has_cycle(macros):
        print("Error: cyclic macro definition", file=sys.stderr)
        sys.exit(1)
    
    # Keep expanding until no more changes
    prev_text = None
    while prev_text != text:
        prev_text = text
        for cmd, replacement in macros.items():
            # Match exact command name, not partial
            pattern = r'\\\\' + re.escape(cmd) + r'(?![A-Za-z])'
            text = re.sub(pattern, replacement, text)
    
    return text

def has_cycle(macros):
    """Check if macro definitions form a cycle."""
    # Build dependency graph
    for cmd in macros:
        visited = set()
        if dfs_cycle(cmd, macros, visited, set()):
            return True
    return False

def dfs_cycle(cmd, macros, visited, rec_stack):
    """DFS to detect cycles in macro dependencies."""
    visited.add(cmd)
    rec_stack.add(cmd)
    
    if cmd in macros:
        replacement = macros[cmd]
        # Find all macro references in replacement
        for other_cmd in macros:
            if other_cmd != cmd:
                pattern = r'\\\\' + re.escape(other_cmd) + r'(?![A-Za-z])'
                if re.search(pattern, replacement):
                    if other_cmd not in visited:
                        if dfs_cycle(other_cmd, macros, visited, rec_stack):
                            return True
                    elif other_cmd in rec_stack:
                        return True
    
    rec_stack.remove(cmd)
    return False

def process_display_math(text):
    r"""Process display math \[ ... \] across the text."""
    lines = text.split('\n')
    result = []
    i = 0
    in_math = False
    math_lines = []
    
    while i < len(lines):
        line = lines[i]
        
        if not in_math:
            # Process all same-line display math on this line
            # But also detect if there's an unmatched \[ that starts multi-line math
            start = line.find('\\[')
            if start == -1:
                # No display math on this line
                result.append(line)
            else:
                # There might be same-line math, multi-line math, or both
                remaining = line
                pos = 0
                found_unmatched = False
                
                while True:
                    start = remaining.find('\\[', pos)
                    if start == -1:
                        # No more \[ found
                        break
                    
                    # Check if there's a matching \]
                    end = remaining.find('\\]', start + 2)
                    
                    if end == -1:
                        # Unmatched \[ - this starts multi-line math
                        found_unmatched = True
                        before = remaining[:start]
                        if before.strip():
                            result.append(before)
                        # The math content starts after \[
                        math_start = start + 2
                        math_content = remaining[math_start:]
                        if math_content.strip():
                            math_lines = [math_content]
                        else:
                            math_lines = []
                        in_math = True
                        break
                    else:
                        # Same-line display math
                        before = remaining[pos:start]
                        math = remaining[start + 2:end]
                        
                        if before.strip():
                            result.append(before)
                        
                        result.append('$$')
                        result.append(math)
                        result.append('$$')
                        
                        pos = end + 2
                
                if not found_unmatched:
                    # Add remaining text after last same-line math
                    remaining_text = remaining[pos:]
                    if remaining_text.strip():
                        result.append(remaining_text)
        else:
            # We're inside multi-line display math
            end = line.find('\\]')
            if end != -1:
                # Math ends on this line
                math_content = line[:end]
                if math_content.strip():
                    math_lines.append(math_content)
                
                result.append('$$')
                result.extend(math_lines)
                result.append('$$')
                
                # Text after \]
                after = line[end + 2:]
                if after.strip():
                    result.extend(process_line_display_math(after))
                
                in_math = False
                math_lines = []
            else:
                # Still in math
                math_lines.append(line)
        
        i += 1
    
    # If math was never closed, treat remaining as math
    if in_math and math_lines:
        result.append('$$')
        result.extend(math_lines)
        result.append('$$')
    
    return '\n'.join(result)

def process_line_display_math(line):
    r"""Process all \[ ... \] display math expressions on a single line."""
    result = []
    pos = 0
    
    while True:
        start = line.find('\\[', pos)
        if start == -1:
            break
        
        end = line.find('\\]', start + 2)
        if end == -1:
            break
        
        before = line[pos:start]
        math = line[start + 2:end]
        
        if before.strip():
            result.append(before)
        
        result.append('$$')
        result.append(math)
        result.append('$$')
        
        pos = end + 2
    
    # Remaining text after last \]
    remaining = line[pos:]
    if remaining.strip():
        result.append(remaining)
    
    # If nothing was found, return the original line
    if not result:
        if line.strip():
            result.append(line)
        else:
            result.append('')
    
    return result


def process_parbox(text):
    """Process \\parbox{width}{content} commands."""
    result = []
    i = 0
    
    while i < len(text):
        pos = text.find('\\\\parbox', i)
        if pos == -1:
            result.append(text[i:])
            break
        
        # Add text before command
        result.append(text[i:pos])
        
        # Find first brace (width)
        brace1_start = pos + len('\\\\parbox')
        if brace1_start >= len(text) or text[brace1_start] != '{':
            print("Error: malformed parbox command", file=sys.stderr)
            sys.exit(1)
        
        # Match first balanced brace
        depth = 1
        j = brace1_start + 1
        while j < len(text) and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1
        
        if depth != 0:
            print("Error: malformed parbox command", file=sys.stderr)
            sys.exit(1)
        
        # Now find second brace (content)
        brace2_start = j
        if brace2_start >= len(text) or text[brace2_start] != '{':
            print("Error: malformed parbox command", file=sys.stderr)
            sys.exit(1)
        
        # Match second balanced brace
        depth = 1
        k = brace2_start + 1
        while k < len(text) and depth > 0:
            if text[k] == '{':
                depth += 1
            elif text[k] == '}':
                depth -= 1
            k += 1
        
        if depth != 0:
            print("Error: malformed parbox command", file=sys.stderr)
            sys.exit(1)
        
        # Extract content (between brace2_start+1 and k-1)
        content = text[brace2_start + 1:k - 1]
        result.append(content)
        
        i = k
    
    return ''.join(result)


def process_includegraphics(text):
    """Process \\includegraphics commands."""
    result = []
    i = 0
    
    while i < len(text):
        pos = text.find('\\\\includegraphics', i)
        if pos == -1:
            result.append(text[i:])
            break
        
        # Add text before command
        result.append(text[i:pos])
        
        # Check for optional arguments [options]
        after_cmd = pos + len('\\\\includegraphics')
        if after_cmd < len(text) and text[after_cmd] == '[':
            # Skip optional arguments
            depth = 1
            j = after_cmd + 1
            while j < len(text) and depth > 0:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                j += 1
            after_cmd = j
        
        # Now expect {path}
        if after_cmd >= len(text) or text[after_cmd] != '{':
            print("Error: malformed includegraphics command", file=sys.stderr)
            sys.exit(1)
        
        # Match balanced brace
        depth = 1
        j = after_cmd + 1
        while j < len(text) and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1
        
        if depth != 0:
            print("Error: malformed includegraphics command", file=sys.stderr)
            sys.exit(1)
        
        # Extract path
        path = text[after_cmd + 1:j - 1]
        result.append(f'![image]({path})')
        
        i = j
    
    return ''.join(result)

def process_environments(text):
    """Process enumerate, itemize, multicols, and minipage environments."""
    result = []
    lines = text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check for multicols
        if stripped.startswith('\\\\begin{multicols}'):
            # Collect multicols content
            content, consumed = collect_environment(lines, i, 'multicols')
            # Just add the content without the wrapper
            result.extend(content)
            i += consumed
            continue
        
        # Check for minipage
        if stripped.startswith('\\\\begin{minipage}'):
            # Collect minipage content
            content, consumed = collect_environment(lines, i, 'minipage')
            # Just add the content without the wrapper
            result.extend(content)
            i += consumed
            continue
        
        # Check for enumerate
        if stripped.startswith('\\begin{enumerate}'):
            # Parse options
            start_num = 1
            options_match = re.match(r'\\begin{enumerate}(\[.*\])?', stripped)
            if options_match and options_match.group(1):
                option_str = options_match.group(1)
                if re.match(r'^\[start=\d+\]$', option_str):
                    start_num = int(option_str[7:-1])  # Extract N from [start=N]
                else:
                    print("Error: unsupported enumerate options", file=sys.stderr)
                    sys.exit(1)
            
            # Collect enumerate content
            enum_content, consumed = collect_environment(lines, i, 'enumerate')
            
            # Process the enumerate content
            processed = process_enumerate(enum_content, start_num, 0, None)
            result.extend(processed)
            
            i += consumed
            continue
        
        # Check for itemize
        if stripped.startswith('\\begin{itemize}'):
            # Collect itemize content
            item_content, consumed = collect_environment(lines, i, 'itemize')
            
            # Process the itemize content
            processed = process_itemize(item_content)
            result.extend(processed)
            
            i += consumed
            continue
        
        result.append(line)
        i += 1
    
    return '\n'.join(result)

def collect_environment(lines, start_idx, env_name):
    """Collect all lines inside an environment, handling nesting."""
    content = []
    i = start_idx + 1
    depth = 1
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if stripped.startswith(f'\\begin{{{env_name}}}'):
            depth += 1
        elif stripped == f'\\end{{{env_name}}}':
            depth -= 1
            if depth == 0:
                return content, i - start_idx + 1
        
        content.append(line)
        i += 1
    
    # Unclosed environment
    return content, i - start_idx

def process_enumerate(lines, start_num, nest_level, parent_num):
    """Process enumerate content, returning list of output lines."""
    result = []
    i = 0
    item_num = start_num
    current_item_num = None
    prev_was_item = False
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check for nested enumerate
        if stripped.startswith('\\begin{enumerate}'):
            if nest_level >= 1:
                print("Error: enumerate nesting deeper than one level", file=sys.stderr)
                sys.exit(1)
            
            # Parse options for nested enumerate
            nested_start = 1
            options_match = re.match(r'\\begin{enumerate}(\[.*\])?', stripped)
            if options_match and options_match.group(1):
                option_str = options_match.group(1)
                if re.match(r'^\[start=\d+\]$', option_str):
                    nested_start = int(option_str[7:-1])
                else:
                    print("Error: unsupported enumerate options", file=sys.stderr)
                    sys.exit(1)
            
            # Collect nested enumerate content
            nested_content, consumed = collect_environment(lines, i, 'enumerate')
            
            # Process nested enumerate - use current_item_num as parent
            nested_result = process_enumerate(nested_content, nested_start, nest_level + 1, current_item_num)
            result.extend(nested_result)
            
            prev_was_item = False  # Nested block doesn't count as item
            i += consumed
            continue
        
        # Check for nested itemize
        if stripped.startswith('\\begin{itemize}'):
            # Collect nested itemize content
            item_content, consumed = collect_environment(lines, i, 'itemize')
            
            # Process nested itemize
            item_result = process_itemize(item_content)
            result.extend(item_result)
            
            prev_was_item = False  # Nested block doesn't count as item
            i += consumed
            continue
        
        # Check for item
        if stripped.startswith('\\item'):
            content = stripped[5:].strip()
            if content:
                # Apply conversions to the item content
                content = apply_conversions(content)
            
            current_item_num = item_num
            
            if nest_level == 0:
                # Top-level item
                if prev_was_item:
                    result.append('')  # Blank line between consecutive items
                result.append(f'**{item_num}.** {content}')
            else:
                # Nested item - use letter
                letter = number_to_letter(item_num - start_num)  # 0-indexed for letter
                if prev_was_item:
                    result.append('')  # Blank line between consecutive nested items
                result.append(f'**{parent_num}.{letter})** {content}')
            
            item_num += 1
            prev_was_item = True
            i += 1
            continue
        
        # Regular line - add if not empty (or preserve empty lines)
        if stripped:
            result.append(line)
        prev_was_item = False
        i += 1
    
    return result

def number_to_letter(n):
    """Convert 0-based number to letter sequence (a, b, ..., z, a, ...)."""
    return chr(ord('a') + (n % 26))

def process_itemize(lines):
    """Process itemize content, returning list of output lines."""
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check for nested enumerate
        if stripped.startswith('\\begin{enumerate}'):
            # Parse options
            start_num = 1
            options_match = re.match(r'\\begin{enumerate}(\[.*\])?', stripped)
            if options_match and options_match.group(1):
                option_str = options_match.group(1)
                if re.match(r'^\[start=\d+\]$', option_str):
                    start_num = int(option_str[7:-1])
                else:
                    print("Error: unsupported enumerate options", file=sys.stderr)
                    sys.exit(1)
            
            # Collect nested enumerate content
            enum_content, consumed = collect_environment(lines, i, 'enumerate')
            
            # Process as standalone top-level enumerate
            enum_result = process_enumerate(enum_content, start_num, 0, None)
            result.extend(enum_result)
            
            i += consumed
            continue
        
        # Check for nested itemize
        if stripped.startswith('\\begin{itemize}'):
            # Collect nested itemize content
            item_content, consumed = collect_environment(lines, i, 'itemize')
            
            # Process nested itemize
            nested_result = process_itemize(item_content)
            result.extend(nested_result)
            
            i += consumed
            continue
        
        # Check for item
        if stripped.startswith('\\item'):
            content = stripped[5:].strip()
            if content:
                # Apply conversions to the item content
                content = apply_conversions(content)
            result.append(f'-   {content}')
            i += 1
            continue
        
        # Regular line
        if stripped:
            result.append(line)
        i += 1
    
    return result

def apply_conversions(text):
    """Apply section, inline formatting, and command deletion conversions."""
    # Command deletion first
    text = re.sub(r'\\vspace\{[^}]*\}', '', text)
    text = re.sub(r'\\medskip', '', text)
    text = re.sub(r'\\smallskip', '', text)
    text = re.sub(r'\\bigskip', '', text)
    
    # Section commands - process innermost first by repeatedly applying
    # We need to handle nested braces properly
    text = apply_command_with_braces(text, '\\section', lambda c: f'## {c}')
    text = apply_command_with_braces(text, '\\subsection', lambda c: f'### {c}')
    text = apply_command_with_braces(text, '\\subsubsection', lambda c: f'#### {c}')
    
    # Inline formatting - process innermost first
    text = apply_command_with_braces(text, '\\emph', lambda c: f'_{c}_')
    text = apply_command_with_braces(text, '\\textbf', lambda c: f'**{c}**')
    
    # Process \\np{...} - remove wrapper, keep inner numeric text
    text = apply_command_with_braces(text, '\\np', lambda c: c)
    
    return text

def apply_command_with_braces(text, cmd, replacer):
    """Apply a command conversion, handling nested braces."""
    result = []
    i = 0
    cmd_len = len(cmd)
    
    while i < len(text):
        # Find the command
        pos = text.find(cmd, i)
        if pos == -1:
            # No more occurrences
            result.append(text[i:])
            break
        
        # Add text before command
        result.append(text[i:pos])
        
        # Find the opening brace
        brace_start = pos + cmd_len
        if brace_start >= len(text) or text[brace_start] != '{':
            # No brace, just skip this command
            result.append(cmd)
            i = pos + cmd_len
            continue
        
        # Match balanced braces
        depth = 1
        j = brace_start + 1
        while j < len(text) and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1
        
        if depth != 0:
            # Unbalanced braces, skip
            result.append(cmd)
            i = pos + cmd_len
            continue
        
        # Extract content (between brace_start+1 and j-1)
        content = text[brace_start + 1:j - 1]
        
        # Apply the conversion
        # But first, recursively apply conversions to the content
        converted_content = apply_conversions(content)
        result.append(replacer(converted_content))
        
        i = j
    
    return ''.join(result)

if __name__ == '__main__':
    main()
