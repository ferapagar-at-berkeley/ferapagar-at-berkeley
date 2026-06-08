#!/usr/bin/env python3
import sys, html, re

# Read git log from stdin
lines = sys.stdin.read().splitlines()

# Custom palette matching a professional dark theme
ANSI_COLORS = {
    '31': '#F85149',    # Red (graph lines)
    '32': '#34D399',    # Green (graph lines)
    '33': '#FBBF24',    # Yellow/Gold (hashes)
    '34': '#60A5FA',    # Blue (graph lines)
    '35': '#FF7F50',    # Magenta/Coral (dates)
    '36': '#22D3EE',    # Cyan (decorations/HEAD)
    '37': '#9CA3AF',    # White/Gray (graph lines)
    
    # Bold / High Intensity
    '1': '#FFFFFF',
    '1;31': '#F85149',
    '1;32': '#34D399',
    '1;33': '#FBBF24',
    '1;34': '#60A5FA',
    '1;35': '#FF7F50',
    '1;36': '#22D3EE',
    
    # High-intensity variants
    '90': '#6B7280',
    '91': '#EF4444',
    '92': '#10B981',
    '93': '#F59E0B',
    '94': '#3B82F6',
    '95': '#EC4899',
    '96': '#06B6D4',
}

font_size = 14
line_height = 22
padding = 20
wrap_limit = 85

ansi_escape = re.compile(r'\x1b\[([0-9;]*)m')

# 1. Parse all lines to extract tokens and colors
parsed_lines_raw = []
for line in lines:
    tokens = []
    current_color = '#E0E0E0'
    last_idx = 0
    for match in ansi_escape.finditer(line):
        start, end = match.start(), match.end()
        text_chunk = line[last_idx:start]
        if text_chunk:
            tokens.append((text_chunk, current_color))
            
        code = match.group(1)
        if code in ('', '0', '39'):
            current_color = '#E0E0E0'
        else:
            current_color = ANSI_COLORS.get(code, current_color)
        last_idx = end
    text_chunk = line[last_idx:]
    if text_chunk:
        tokens.append((text_chunk, current_color))
    parsed_lines_raw.append(tokens)

# Helper to split prefix and content tokens
def split_line(tokens):
    prefix = []
    content = []
    found_hash = False
    for text, color in tokens:
        # A commit hash is exactly 7 characters, hexadecimal, and colored gold (#FBBF24)
        is_hash = (color == '#FBBF24' and len(text) == 7 and all(c in '0123456789abcdefABCDEF' for c in text))
        if not found_hash and is_hash:
            found_hash = True
        if not found_hash:
            prefix.append((text, color))
        else:
            content.append((text, color))
    if not found_hash:
        return [], tokens
    return prefix, content

all_output_lines = []
skip_indices = set()

# 2. Process wrapping and color look-ahead
for idx in range(len(parsed_lines_raw)):
    if idx in skip_indices:
        continue
        
    tokens = parsed_lines_raw[idx]
    clean_line = ''.join(t[0] for t in tokens)
    if len(clean_line) <= wrap_limit:
        all_output_lines.append(tokens)
    else:
        prefix_tokens, content_tokens = split_line(tokens)
        prefix_len = sum(len(t[0]) for t in prefix_tokens)
        
        # Calculate wrap limit for content
        max_content_len = wrap_limit - prefix_len - 4
        if max_content_len < 20:
            max_content_len = 20
            
        # Split content into wrapped chunks
        chunks = []
        current_chunk = []
        current_len = 0
        for text, color in content_tokens:
            pos = 0
            while pos < len(text):
                rem_space = max_content_len - current_len
                
                # Check if this token is a date (#FF7F50) or a short unit that won't fit.
                # If so, push the current chunk immediately and start a new one to prevent splitting it.
                is_date = (color == '#FF7F50')
                entire_token_len = len(text) - pos
                if (is_date or entire_token_len < 12) and entire_token_len > rem_space and current_len > 0:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_len = 0
                    rem_space = max_content_len
                
                chunk = text[pos:pos+rem_space]
                
                if pos + len(chunk) < len(text) and ' ' in chunk:
                    last_space = chunk.rfind(' ')
                    if last_space > 0:
                        chunk = chunk[:last_space+1]
                        
                if len(chunks) > 0 and current_len == 0:
                    chunk = chunk.lstrip()
                    
                current_chunk.append((chunk, color))
                current_len += len(chunk)
                pos += len(chunk)
                
                if current_len >= max_content_len or pos < len(text):
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_len = 0
        if current_len > 0:
            chunks.append(current_chunk)
            
        # Append the first line
        first_line = list(prefix_tokens) + chunks[0]
        all_output_lines.append(first_line)
        
        # Process the remaining wrapped chunks
        chunk_idx = 1
        lookahead_idx = idx + 1
        while chunk_idx < len(chunks):
            # Check if the next line is a graph-only line
            is_graph_only = False
            if lookahead_idx < len(parsed_lines_raw):
                next_tokens = parsed_lines_raw[lookahead_idx]
                next_prefix, next_content = split_line(next_tokens)
                
                # If there's no hash on the next line, it is a graph-only line
                if len(next_prefix) == 0 and not any(
                    (color == '#FBBF24' and len(text) == 7 and all(c in '0123456789abcdefABCDEF' for c in text))
                    for text, color in next_tokens
                ):
                    is_graph_only = True
            
            if is_graph_only:
                # Merge into the existing graph-only line instead of inserting a new line
                merged_line = list(next_tokens) + [('    ', '#E0E0E0')] + chunks[chunk_idx]
                all_output_lines.append(merged_line)
                skip_indices.add(lookahead_idx)
                lookahead_idx += 1
                chunk_idx += 1
            else:
                # No graph-only line available. Build a new wrapped line prefix
                next_prefix_colors = []
                if lookahead_idx < len(parsed_lines_raw):
                    next_prefix, _ = split_line(parsed_lines_raw[lookahead_idx])
                    next_prefix_colors = [color for _, color in next_prefix]
                    
                wrap_prefix_tokens = []
                for j, (text, color) in enumerate(prefix_tokens):
                    wrap_text = text.replace('*', '|')
                    use_color = color
                    if j < len(next_prefix_colors) and next_prefix_colors[j] != '#E0E0E0':
                        use_color = next_prefix_colors[j]
                    elif color != '#E0E0E0':
                        use_color = color
                    wrap_prefix_tokens.append((wrap_text, use_color))
                    
                wrap_prefix_tokens.append(('    ', '#E0E0E0'))
                
                new_line = wrap_prefix_tokens + chunks[chunk_idx]
                all_output_lines.append(new_line)
                chunk_idx += 1

# Calculate dimensions
max_chars = max(sum(len(t[0]) for t in line) for line in all_output_lines)
width = int(max_chars * 8.2) + (padding * 2)
height = len(all_output_lines) * line_height + (padding * 2)

svg = []
# Ensure xml:space="preserve" is set on the root <svg> and individual <text> tags so browsers preserve indent spaces
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" xml:space="preserve">')
svg.append(f'  <rect width="100%" height="100%" fill="#0d1117" rx="6" />')
svg.append(f'  <g font-family="Consolas, Monaco, Fira Code, Courier New, monospace" font-size="{font_size}px">')

y = padding + font_size - 4
for line_tokens in all_output_lines:
    svg_line = [f'    <text x="{padding}" y="{y}" xml:space="preserve">']
    for text, color in line_tokens:
        escaped_text = html.escape(text)
        svg_line.append(f'<tspan fill="{color}">{escaped_text}</tspan>')
    svg_line.append('</text>')
    svg.append(''.join(svg_line))
    y += line_height

svg.append('  </g>')
svg.append('</svg>')

# Save output to timeline.svg
with open('timeline.svg', 'w') as f:
    f.write("\n".join(svg))
print("Successfully generated timeline.svg!")
