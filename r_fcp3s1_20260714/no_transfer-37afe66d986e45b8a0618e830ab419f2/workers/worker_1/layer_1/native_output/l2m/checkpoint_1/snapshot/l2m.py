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
    
    if begin_doc in full_text:
        start = full_text.find(begin_doc)
        start_idx = start + len(begin_doc)
        
        end_idx = full_text.find(end_doc, start_idx)
        if end_idx == -1:
            body = full_text[start_idx:]
        else:
            body = full_text[start_idx:end_idx]
    else:
        body = full_text
    
    # Strip leading/trailing whitespace from body to avoid extra newlines
    body = body.strip(' \t\n\r')
    
    # Step 3: Process display math (multi-line and same-line)
    body = process_display_math(body)
    
    # Step 4: Line stripping
    body_lines = body.split('\n')
    stripped_lines = [line.strip(' \t') for line in body_lines]
    
    # Step 5: Process each line for other conversions
    result_lines = []
    for line in stripped_lines:
        converted_line = apply_conversions(line)
        result_lines.append(converted_line)
    
    # Step 6: Blank line normalization
    text = '\n'.join(result_lines)
    
    # Collapse runs of 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip leading/trailing whitespace from final output
    text = text.strip(' \t\n\r')
    
    return text

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
