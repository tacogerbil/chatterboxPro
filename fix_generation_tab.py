import re

# Read the file
with open(r'a:\Coding_Projects\AI Coding\ChatterboxPro\execution\chatterboxPro\ui\tabs\generation_tab.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Process each line
output_lines = []
for i, line in enumerate(lines):
    # Skip lines before row 28 (after the container setup)
    if i < 28:
        output_lines.append(line)
        continue
    
    # Replace widget instantiations that use (self,
    # Match patterns like: ctk.CTkFrame(self, or LabeledSlider(self,
    if re.search(r'(ctk\.CTk\w+|LabeledSlider)\(self,', line):
        line = re.sub(r'(ctk\.CTk\w+|LabeledSlider)\(self,', r'\1(self.scroll_container,', line)
    
    output_lines.append(line)

# Write back
with open(r'a:\Coding_Projects\AI Coding\ChatterboxPro\execution\chatterboxPro\ui\tabs\generation_tab.py', 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print("Fixed generation_tab.py")
